import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { runtime } from './runtime';
import type { Purpose, PurposeView, Scenario, StoryStepLink } from '$lib/types';

const TABLE_ROW_PREFIX = '| `';
const RULES_HEADING = '## Purpose Rules';

/**
 * Parse `docs/purposes.md` in full: both the wave 1 purpose table and the
 * plain-language rule paragraph under "## Purpose Rules" for each purpose. The
 * page renders exclusively from this parse, so no purpose prose is duplicated in
 * component code.
 */
export function parsePurposes(raw: string): Purpose[] {
  const rules = parseRuleParagraphs(raw);
  return raw
    .split('\n')
    .filter((line) => line.startsWith(TABLE_ROW_PREFIX) && [5, 7].includes(line.split('|').length))
    .map((line) => {
      const cells = line.split('|').slice(1, -1).map((cell) => cell.trim());
      const iri = stripTicks(cells[0]);
      const slug = iri.split('/').pop() ?? iri;
      if (cells.length === 3) {
        return {
          iri,
          slug,
          advertisedBy: cells[1],
          enforcedBy: 'Authority Evidence gateways',
          story: slug.replace(/-/g, ' '),
          denialCodes: ['not_authorized'],
          plainLanguage: `${cells[1]} may answer this purpose through ${cells[2]}. Wrong-purpose and unauthorized requests disclose nothing.`
        };
      }
      return {
        iri,
        slug,
        advertisedBy: cells[1],
        enforcedBy: stripTicks(cells[2]),
        story: cells[3],
        denialCodes: [...cells[4].matchAll(/`([^`]+)`/g)].map((match) => match[1]),
        plainLanguage: rules[slug] ?? ''
      };
    });
}

/**
 * Split the "## Purpose Rules" section into one plain-language paragraph per
 * purpose. Each paragraph opens with the purpose slug in backticks, so the slug
 * keys the paragraph back to its table row.
 */
function parseRuleParagraphs(raw: string): Record<string, string> {
  const start = raw.indexOf(RULES_HEADING);
  if (start === -1) return {};
  const afterHeading = raw.slice(start + RULES_HEADING.length);
  const nextHeading = afterHeading.indexOf('\n## ');
  const section = nextHeading === -1 ? afterHeading : afterHeading.slice(0, nextHeading);
  const rules: Record<string, string> = {};
  for (const paragraph of section.split(/\n\s*\n/)) {
    const trimmed = paragraph.trim();
    const match = trimmed.match(/^`([a-z0-9-]+)`/);
    if (!match) continue;
    rules[match[1]] = trimmed.replace(/`/g, '').replace(/\s+/g, ' ').trim();
  }
  return rules;
}

export async function readPurposes(): Promise<Purpose[]> {
  const raw = await readFile(path.join(runtime.labRoot, 'docs/purposes.md'), 'utf-8');
  return parsePurposes(raw);
}

/**
 * Return the guided-story steps that demonstrate a purpose, matched on the
 * Evidence `purpose` member each step's request preview actually sends. This keeps
 * the story cross-links driven by the scenario data rather than a hand table.
 */
export function storyLinksForPurpose(iri: string, scenarios: Scenario[]): StoryStepLink[] {
  const links: StoryStepLink[] = [];
  for (const scenario of scenarios) {
    for (const step of scenario.steps) {
      const preview = step.request_preview;
      const body = preview?.body && typeof preview.body === 'object' ? preview.body as Record<string, unknown> : {};
      const sent = preview?.purpose ?? body.purpose;
      if (sent === iri) {
        links.push({ storyId: scenario.id, storyTitle: scenario.title, stepId: step.id, stepLabel: step.label });
      }
    }
  }
  return links;
}

export function buildPurposeViews(purposes: Purpose[], scenarios: Scenario[]): PurposeView[] {
  return purposes.map((purpose) => ({ ...purpose, storyLinks: storyLinksForPurpose(purpose.iri, scenarios) }));
}

function stripTicks(value: string): string {
  return value.replace(/`/g, '');
}
