import { env } from '$env/dynamic/private';
import type { ConfigLink, TopologyGroup, TopologyService } from '$lib/types';

/**
 * The one env-driven service table for the visitor center. Every server-side
 * probe URL, every anatomy config link, and the status grid read from here so no
 * port or hostname is scattered across components. Probe URLs default to the
 * published localhost ports and are overridden by the compose-internal URLs the
 * home container receives (see the `home` service env in `compose.yaml`), which
 * is why Relay, Evidence, and Mint are reachable for probing from the network.
 *
 * The internal probe origins mirror the same conventions as `urlmap.ts` and
 * `scenarios/service_config.py`.
 */
export type ServiceRole = 'shared' | 'relay' | 'evidence';

type ServiceStatusSemantics = 'health' | 'auth-gated';

type ServiceDef = {
  id: string;
  label: string;
  role: ServiceRole;
  authority?: string;
  purpose?: string;
  blurb: string;
  probeEnv?: string;
  probeDefault?: string;
  probePath?: string;
  semantics: ServiceStatusSemantics;
  self?: boolean;
  browsable?: boolean;
  configPaths: { label: string; path: string }[];
};

export const SERVICES: ServiceDef[] = [
  {
    id: 'metadata',
    label: 'Published metadata',
    role: 'shared',
    blurb: 'Serves the CPSV-AP metadata bundle that the Nation grid and the explorer render from.',
    probeEnv: 'STATIC_METADATA_URL',
    probeDefault: 'http://127.0.0.1:4331',
    probePath: '/.well-known/api-catalog',
    semantics: 'health',
    browsable: true,
    configPaths: [
      { label: 'Assembly manifest', path: 'metadata/assembly.yaml' },
      { label: 'Published bundle', path: 'metadata/public' }
    ]
  },
  {
    id: 'scenario-runner',
    label: 'Scenario runner',
    role: 'shared',
    blurb: 'Runs the guided stories and the Purpose Lens against Registry Evidence.',
    probeEnv: 'SCENARIO_RUNNER_URL',
    probeDefault: 'http://127.0.0.1:4302',
    probePath: '/health',
    semantics: 'health',
    configPaths: [
      { label: 'Runner API', path: 'scenario-runner/server.py' },
      { label: 'Scenario modules', path: 'scenarios' }
    ]
  },
  {
    id: 'portal',
    label: 'Citizen portal',
    role: 'shared',
    blurb: 'The in-fiction resident application. Solmara Lab hands personas into it.',
    probeEnv: 'PORTAL_PROBE_URL',
    probeDefault: 'http://127.0.0.1:4300',
    probePath: '/',
    semantics: 'health',
    browsable: true,
    configPaths: [{ label: 'Portal app', path: 'portal' }]
  },
  {
    id: 'home',
    label: 'Solmara Lab',
    role: 'shared',
    blurb: 'The out-of-fiction front door to the live synthetic country.',
    semantics: 'health',
    self: true,
    browsable: true,
    configPaths: [{ label: 'Home app', path: 'home' }]
  },
  {
    id: 'cra-civil-relay',
    label: 'CRA civil relay',
    role: 'relay',
    authority: 'Civil Registration Authority',
    blurb: 'Read-only relay over civil registration (births, deaths).',
    probeEnv: 'CRA_CIVIL_RELAY_URL',
    probeDefault: 'http://127.0.0.1:4311',
    probePath: '/',
    semantics: 'auth-gated',
    configPaths: [
      { label: 'Registry project', path: 'projects/cra-civil/registry-stack.yaml' },
      { label: 'Generated Relay config', path: 'runtime/registry-projects/local/cra-civil/relay/relay.yaml' },
      { label: 'Seed and fixtures', path: 'ministries/interior-civil' }
    ]
  },
  {
    id: 'nia-population-relay',
    label: 'NIA population relay',
    role: 'relay',
    authority: 'National Identity Agency',
    blurb: 'Read-only relay over the population register.',
    probeEnv: 'NIA_POPULATION_RELAY_URL',
    probeDefault: 'http://127.0.0.1:4312',
    probePath: '/',
    semantics: 'auth-gated',
    configPaths: [
      { label: 'Registry project', path: 'projects/nia-population/registry-stack.yaml' },
      { label: 'Generated Relay config', path: 'runtime/registry-projects/local/nia-population/relay/relay.yaml' },
      { label: 'Seed and fixtures', path: 'ministries/interior-population' }
    ]
  },
  {
    id: 'sro-social-relay',
    label: 'SRO social relay',
    role: 'relay',
    authority: 'Social Registry Office',
    blurb: 'Read-only relay over the social registry (household poverty band).',
    probeEnv: 'SRO_SOCIAL_RELAY_URL',
    probeDefault: 'http://127.0.0.1:4313',
    probePath: '/',
    semantics: 'auth-gated',
    configPaths: [
      { label: 'Registry project', path: 'projects/sro-social/registry-stack.yaml' },
      { label: 'Generated Relay config', path: 'runtime/registry-projects/local/sro-social/relay/relay.yaml' },
      { label: 'Seed and fixtures', path: 'ministries/social-development' }
    ]
  },
  {
    id: 'programme-mis-relay',
    label: 'Programme MIS relay',
    role: 'relay',
    authority: 'Ministry of Social Development Programme MIS',
    blurb: 'Read-only relay over the integrated beneficiary registry.',
    probeEnv: 'PROGRAMME_MIS_RELAY_URL',
    probeDefault: 'http://127.0.0.1:4314',
    probePath: '/',
    semantics: 'auth-gated',
    configPaths: [
      { label: 'Registry project', path: 'projects/mosd-programme/registry-stack.yaml' },
      { label: 'Generated Relay config', path: 'runtime/registry-projects/local/mosd-programme/relay/relay.yaml' },
      { label: 'Seed and fixtures', path: 'ministries/social-development' }
    ]
  },
  {
    id: 'sipf-pensions-relay',
    label: 'SIPF pensions relay',
    role: 'relay',
    authority: 'Social Insurance and Pensions Fund',
    blurb: 'Read-only relay over pension case records.',
    probeEnv: 'SIPF_PENSIONS_RELAY_URL',
    probeDefault: 'http://127.0.0.1:4315',
    probePath: '/',
    semantics: 'auth-gated',
    configPaths: [
      { label: 'Registry project', path: 'projects/sipf-pensions/registry-stack.yaml' },
      { label: 'Generated Relay config', path: 'runtime/registry-projects/local/sipf-pensions/relay/relay.yaml' },
      { label: 'Seed and fixtures', path: 'ministries/labour-pensions' }
    ]
  },
  {
    id: 'nagdi-agriculture-relay',
    label: 'NAgDI agriculture relay',
    role: 'relay',
    authority: 'National Agricultural Data Institute',
    blurb: 'Read-only relay over farmer and livestock registries.',
    probeEnv: 'NAGDI_AGRICULTURE_RELAY_URL',
    probeDefault: 'http://127.0.0.1:4316',
    probePath: '/',
    semantics: 'auth-gated',
    configPaths: [
      { label: 'Registry project', path: 'projects/nagdi-agriculture/registry-stack.yaml' },
      { label: 'Generated Relay config', path: 'runtime/registry-projects/local/nagdi-agriculture/relay/relay.yaml' },
      { label: 'Seed and fixtures', path: 'ministries/agriculture-nagdi' }
    ]
  },
  {
    id: 'child-benefit-federator',
    label: 'Child benefit federator',
    role: 'shared',
    purpose: 'child-benefit-review',
    blurb: 'Collects minimized source-owned predicates as ordinary application evidence. It does not make the eligibility decision.',
    probeEnv: 'CHILD_BENEFIT_FEDERATOR_URL',
    probeDefault: 'http://127.0.0.1:4321',
    probePath: '/health',
    semantics: 'health',
    configPaths: [{ label: 'Federator service', path: 'scenario-runner/child_benefit_federator.py' }]
  },
  {
    id: 'registry-evidence',
    label: 'Registry Evidence',
    role: 'evidence',
    purpose: 'all six reviewed Solmara purposes',
    blurb: 'Evaluates eleven minimized requirements against authority Records APIs and returns signed evidence assertions.',
    probeEnv: 'EVIDENCE_URL',
    probeDefault: 'https://localhost:4341',
    probePath: '/health',
    semantics: 'health',
    configPaths: [
      { label: 'Runtime config', path: 'evidence/runtime.yaml' },
      { label: 'Evidence bundle', path: 'evidence/bundle' }
    ]
  },
  {
    id: 'registry-mint',
    label: 'Registry Mint',
    role: 'evidence',
    blurb: 'Issues short-lived requester-bound access tokens for the local Evidence service using private_key_jwt.',
    probeEnv: 'MINT_URL',
    probeDefault: 'https://localhost:4341',
    probePath: '/health',
    semantics: 'health',
    configPaths: [{ label: 'Mint config', path: 'evidence/mint.yaml' }]
  }
];

export type StatusProbe = {
  id: string;
  label: string;
  role: ServiceRole;
  self: boolean;
  probeUrl?: string;
  href?: string;
};

/**
 * Resolve the concrete probe URL and visitor-facing "Open" link for each
 * service. `portalUrl` is the browser-facing portal origin used for the Open
 * link, while the probe still targets the compose-internal portal URL.
 */
export function statusProbes(portalUrl: string, readEnv: Record<string, string | undefined> = env): StatusProbe[] {
  return SERVICES.map((service) => {
    const base = service.probeEnv ? readEnv[service.probeEnv] ?? service.probeDefault : undefined;
    const probeUrl = base && service.probePath ? joinUrl(base, service.probePath) : undefined;
    let href: string | undefined;
    if (service.browsable) {
      if (service.id === 'metadata') href = '/.well-known/api-catalog';
      else if (service.id === 'portal') href = portalUrl;
      else if (service.id === 'home') href = '/';
    }
    return { id: service.id, label: service.label, role: service.role, self: Boolean(service.self), probeUrl, href };
  });
}

/**
 * Group the topology for the anatomy page: authority Relays, the Evidence and
 * Mint trust boundary, and shared application services.
 * Config paths become repo links, with the
 * in-repo relative path preserved as visible text.
 */
export function topologyGroups(repoUrl: string): TopologyGroup[] {
  const shared = SERVICES.filter((service) => service.role === 'shared');
  const relays = SERVICES.filter((service) => service.role === 'relay');
  const evidence = SERVICES.filter((service) => service.role === 'evidence');
  return [
    {
      key: 'relays',
      title: 'One Relay per authority',
      blurb:
        'Each authority runs its own Relay over data it already holds. Nothing is copied into a central store, so a compromise or outage is contained to a single authority and each audit chain stays independent.',
      services: relays.map((service) => toTopologyService(service, repoUrl))
    },
    {
      key: 'evidence',
      title: 'Evidence and requester identity',
      blurb:
        'Evidence evaluates reviewed requirements against protected Records APIs and signs the minimized values. Mint supplies short-lived requester identity and grant tags. Neither service owns an application decision.',
      services: evidence.map((service) => toTopologyService(service, repoUrl))
    },
    {
      key: 'shared',
      title: 'Shared services',
      blurb: 'The pieces every authority leans on: metadata publishing, scenario execution, and the two front doors.',
      services: shared.map((service) => toTopologyService(service, repoUrl))
    }
  ];
}

function toTopologyService(service: ServiceDef, repoUrl: string): TopologyService {
  return {
    id: service.id,
    label: service.label,
    role: service.role,
    authority: service.authority,
    purpose: service.purpose,
    blurb: service.blurb,
    config: service.configPaths.map((entry) => configLink(entry.label, entry.path, repoUrl))
  };
}

function configLink(label: string, path: string, repoUrl: string): ConfigLink {
  const kind = path.split('/').pop()?.includes('.') ? 'blob' : 'tree';
  return { label, path, url: `${repoUrl}/${kind}/main/${path}` };
}

function joinUrl(base: string, path: string): string {
  return `${base.replace(/\/$/, '')}/${path.replace(/^\//, '')}`;
}
