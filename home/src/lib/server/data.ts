import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { runtime, joinedUrl } from './runtime';
import { buildPublicUrlMap, mapPublicUrl } from './urlmap';
import { statusProbes } from './services';
import { readSeedSummary, readSmokeEvidence } from './evidence';
import { buildCurlExamples, parsePublishedTokens } from './tokens';
import { readPurposes } from './purposes';
import type { ChangelogEntry, ChangelogFullEntry, HomeData, MetadataBundle, Persona, Scenario, StatusItem } from '$lib/types';

type FetchLike = typeof fetch;

export { readPurposes } from './purposes';

export async function loadHomeData(fetcher: FetchLike = fetch): Promise<HomeData> {
  const [metadata, scenarioResult, purposes, personas, districts, provinces, country, services, versions, status, smoke, seed, changelogLatest] =
    await Promise.all([
      fetchMetadata(fetcher),
      fetchScenarios(fetcher),
      readPurposes(),
      readPersonas(),
      readJson('geo/districts.geojson'),
      readJson('geo/provinces.geojson'),
      readJson('geo/country.geojson'),
      readComposeServices(),
      readVersions(),
      readStatus(fetcher),
      readSmokeEvidence(),
      readSeedSummary(),
      readChangelogLatest()
    ]);

  const publishedTokens = parsePublishedTokens();

  return {
    metadata,
    scenarios: scenarioResult.scenarios,
    defaultScenarioId: scenarioResult.defaultScenarioId,
    purposes,
    personas,
    districts,
    provinces,
    country,
    status,
    services,
    versions,
    smoke,
    seed,
    publishedTokens,
    curlExamples: buildCurlExamples(publishedTokens),
    changelogLatest,
    repoUrl: runtime.repoUrl,
    generatedAt: new Date().toISOString(),
    portalUrl: runtime.portalUrl
  };
}

/**
 * Read the newest changelog entry heading from `docs/changelog.md`. The file
 * uses `## YYYY-MM-DD Title` per entry; the first such heading is the latest.
 * Returns null when the file is absent so the trust strip can stay quiet.
 */
export async function readChangelogLatest(): Promise<ChangelogEntry | null> {
  let raw: string;
  try {
    raw = await readText('docs/changelog.md');
  } catch {
    return null;
  }
  for (const line of raw.split('\n')) {
    const match = line.match(/^##\s+(\d{4}-\d{2}-\d{2})\s+(.+?)\s*$/);
    if (match) {
      return { date: match[1], title: match[2], href: '/changelog' };
    }
  }
  return null;
}

/** Parse every `## YYYY-MM-DD Title` entry with its body paragraph. */
export async function readChangelog(): Promise<ChangelogFullEntry[]> {
  let raw: string;
  try {
    raw = await readText('docs/changelog.md');
  } catch {
    return [];
  }
  const entries: ChangelogFullEntry[] = [];
  const lines = raw.split('\n');
  let current: ChangelogFullEntry | null = null;
  for (const line of lines) {
    const match = line.match(/^##\s+(\d{4}-\d{2}-\d{2})\s+(.+?)\s*$/);
    if (match) {
      if (current) entries.push(current);
      current = { date: match[1], title: match[2], body: '' };
    } else if (current) {
      current.body += (current.body ? ' ' : '') + line.trim();
    }
  }
  if (current) entries.push(current);
  return entries.map((entry) => ({ ...entry, body: entry.body.replace(/\s+/g, ' ').trim() }));
}

/**
 * Fetch a single guided scenario with its per-step request previews, rewriting
 * every internal compose URL to a host-reachable one so the story page and its
 * copy-as-curl snippets are curlable by a visitor. Returns null when the
 * scenario runner is unavailable or the id is unknown.
 */
export async function loadScenario(id: string, fetcher: FetchLike = fetch): Promise<Scenario | null> {
  try {
    const detail = await fetchJson(fetcher, joinedUrl(runtime.scenarioRunnerUrl, `/v1/scenarios/${id}`));
    const story = detail.story as Scenario | undefined;
    if (!story) return null;
    return mapScenarioUrls(story);
  } catch {
    return null;
  }
}

function mapScenarioUrls(scenario: Scenario): Scenario {
  const map = buildPublicUrlMap();
  return {
    ...scenario,
    steps: scenario.steps.map((step) =>
      step.request_preview
        ? { ...step, request_preview: { ...step.request_preview, url: mapPublicUrl(step.request_preview.url, map) } }
        : step
    )
  };
}

export async function fetchMetadata(fetcher: FetchLike = fetch): Promise<MetadataBundle> {
  try {
    const [apiCatalog, catalog, offeringsPayload, policiesPayload] = await Promise.all([
      fetchJson(fetcher, joinedUrl(runtime.staticMetadataUrl, '/.well-known/api-catalog')),
      fetchJson(fetcher, joinedUrl(runtime.staticMetadataUrl, '/metadata/catalog.json')),
      fetchJson(fetcher, joinedUrl(runtime.staticMetadataUrl, '/metadata/evidence-offerings.json')),
      fetchJson(fetcher, joinedUrl(runtime.staticMetadataUrl, '/metadata/policies.jsonld'))
    ]);
    return {
      available: true,
      apiCatalog,
      catalog: {
        datasets: arrayValue(catalog.datasets),
        gray_registries: arrayValue(catalog.gray_registries),
        authorities: arrayValue(catalog.authorities),
        public_services: arrayValue(catalog.public_services)
      },
      offerings: arrayValue(offeringsPayload.offerings),
      policies: arrayValue(policiesPayload['@graph'])
    };
  } catch (error) {
    return {
      available: false,
      error: error instanceof Error ? error.message : 'metadata unavailable',
      catalog: { datasets: [], gray_registries: [], authorities: [], public_services: [] },
      offerings: [],
      policies: []
    };
  }
}

export async function fetchScenarios(fetcher: FetchLike = fetch): Promise<{ scenarios: Scenario[]; defaultScenarioId: string }> {
  try {
    const summary = await fetchJson(fetcher, joinedUrl(runtime.scenarioRunnerUrl, '/v1/scenarios'));
    const scenarioSummaries = arrayValue(summary.scenarios);
    const details = await Promise.all(
      scenarioSummaries
        .filter((scenario) => typeof scenario.id === 'string' && scenario.id !== 'citizen-self-service')
        .map((scenario) => fetchJson(fetcher, joinedUrl(runtime.scenarioRunnerUrl, `/v1/scenarios/${scenario.id}`)))
    );
    return {
      defaultScenarioId: String(summary.default_scenario_id ?? 'birth-to-child-benefit'),
      scenarios: details
        .map((detail) => detail.story as Scenario)
        .filter(Boolean)
        .map(mapScenarioUrls)
    };
  } catch {
    return { defaultScenarioId: 'birth-to-child-benefit', scenarios: [] };
  }
}

/**
 * Probe every service in the topology table server-side and classify each as
 * up, auth-gated (an authenticated endpoint answering 401/403 without a token,
 * which is the honest "up but gated" signal), or down. The home row is self, so
 * it is reported up without a network call.
 */
export async function readStatus(fetcher: FetchLike = fetch, portalUrl: string = runtime.portalUrl): Promise<StatusItem[]> {
  const probes = statusProbes(portalUrl);
  return Promise.all(
    probes.map(async (probe) => {
      const item: StatusItem = { id: probe.id, label: probe.label, href: probe.href, status: 'down' };
      if (probe.self) return { ...item, status: 'up', httpStatus: 200 };
      if (!probe.probeUrl) return { ...item, status: 'down' };
      try {
        const response = await fetcher(probe.probeUrl, { signal: AbortSignal.timeout(1500) });
        const status = response.status === 401 || response.status === 403 ? 'auth-gated' : response.ok ? 'up' : 'down';
        return { ...item, status, httpStatus: response.status };
      } catch {
        return { ...item, status: 'down' };
      }
    })
  );
}

export async function readPersonas(): Promise<Persona[]> {
  const raw = await readText('generator/output/shared/personas.csv');
  return parseCsv(raw).slice(0, 24).map((row) => ({
    persona_id: row.persona_id ?? '',
    roster_primary_id: row.roster_primary_id ?? '',
    given_name: row.given_name ?? '',
    family_name: row.family_name ?? '',
    role: row.role ?? '',
    district_code: row.district_code ?? ''
  }));
}

export async function readComposeServices(): Promise<string[]> {
  const raw = await readText('compose.yaml');
  const services: string[] = [];
  let insideServices = false;
  for (const line of raw.split('\n')) {
    if (line === 'services:') {
      insideServices = true;
      continue;
    }
    if (insideServices && line && !line.startsWith(' ')) break;
    const match = insideServices ? line.match(/^  ([a-z0-9-]+):$/) : null;
    if (match) services.push(match[1]);
  }
  return services;
}

export async function readVersions(): Promise<Record<string, string>> {
  const raw = await readText('versions.env');
  return Object.fromEntries(
    raw
      .split('\n')
      .map((line) => line.trim())
      .filter((line) => line && !line.startsWith('#') && line.includes('='))
      .map((line) => {
        const [key, ...rest] = line.split('=');
        return [key, rest.join('=')];
      })
  );
}

async function fetchJson(fetcher: FetchLike, url: string): Promise<Record<string, unknown>> {
  const response = await fetcher(url, { signal: AbortSignal.timeout(2000) });
  if (!response.ok && response.status !== 401 && response.status !== 403) {
    throw new Error(`${url} returned HTTP ${response.status}`);
  }
  return (await response.json()) as Record<string, unknown>;
}

async function readJson(relative: string): Promise<Record<string, unknown>> {
  return JSON.parse(await readText(relative)) as Record<string, unknown>;
}

async function readText(relative: string): Promise<string> {
  return readFile(path.join(runtime.labRoot, relative), 'utf-8');
}

function parseCsv(raw: string): Record<string, string>[] {
  const [headerLine, ...lines] = raw.trim().split('\n');
  const headers = splitCsvLine(headerLine);
  return lines.map((line) => Object.fromEntries(splitCsvLine(line).map((value, index) => [headers[index], value])));
}

function splitCsvLine(line: string): string[] {
  const values: string[] = [];
  let current = '';
  let quoted = false;
  for (let index = 0; index < line.length; index += 1) {
    const char = line[index];
    if (char === '"') {
      quoted = !quoted;
    } else if (char === ',' && !quoted) {
      values.push(current);
      current = '';
    } else {
      current += char;
    }
  }
  values.push(current);
  return values;
}

function arrayValue(value: unknown): any[] {
  return Array.isArray(value) ? value : [];
}
