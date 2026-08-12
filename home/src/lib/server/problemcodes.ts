import type { ProblemCode, Purpose, Scenario, StoryStepLink } from '$lib/types';

/**
 * Static, maintained metadata for every stable problem code the lab can emit.
 * The `typeUri` values are the problem type URIs emitted by Registry Evidence
 * responses. The set of codes is assembled from the purpose catalogue (which
 * lists each purpose's denial codes) plus these entries, so the page never
 * hand-maintains prose that can drift from the catalogue. Meanings are plain
 * English with the product terms explained inline.
 */
const CODE_META: Record<
  string,
  { title: string; status: number; typeUri: string; meaning: string; coverage?: string }
> = {
  not_authorized: {
    title: 'Purpose not permitted',
    status: 403,
    typeUri: 'https://registrystack.org/problems/evidence/not_authorized',
    meaning:
      'The requester grant does not authorize this requirement, purpose, response format, or selector shape. Registry Evidence refuses before source access and discloses nothing.'
  },
  malformed_request: {
    title: 'Invalid evidence request',
    status: 400,
    typeUri: 'https://registrystack.org/problems/evidence/malformed_request',
    meaning:
      'The request does not match the closed Evidence request contract. Registry Evidence rejects it before evaluating a requirement.',
    coverage: 'Covered by the Evidence bundle fixtures and v0.18.0 contract tests.'
  }
};

/** Steps whose id marks them as a purpose denial demonstrate not_authorized. */
function denialSteps(scenarios: Scenario[]): StoryStepLink[] {
  const links: StoryStepLink[] = [];
  for (const scenario of scenarios) {
    for (const step of scenario.steps) {
      if (step.id.includes('denial')) {
        links.push({ storyId: scenario.id, storyTitle: scenario.title, stepId: step.id, stepLabel: step.label });
      }
    }
  }
  return links;
}

/**
 * Assemble the problem-code reference from maintained sources: the union of
 * every purpose's denial codes plus the known problem type URIs. Each code
 * carries its plain-language meaning, the purposes that reference it, the story
 * steps that demonstrate it, and an example problem+json body (RFC 9457).
 */
export function assembleProblemCodes(purposes: Purpose[], scenarios: Scenario[]): ProblemCode[] {
  const codes = new Set<string>();
  for (const purpose of purposes) {
    for (const code of purpose.denialCodes) codes.add(code);
  }
  for (const code of Object.keys(CODE_META)) codes.add(code);

  const denials = denialSteps(scenarios);

  return [...codes]
    .sort()
    .map((code) => {
      const meta = CODE_META[code] ?? {
        title: code,
        status: 400,
        typeUri: `https://registrystack.org/problems/evidence/${code.replace(/\./g, '_')}`,
        meaning: 'A stable problem code emitted by the stack. See the purpose catalogue for where it applies.'
      };
      const typeUri = meta.typeUri;
      const purposeSlugs = purposes.filter((purpose) => purpose.denialCodes.includes(code)).map((purpose) => purpose.slug);
      const demonstratedBy = code === 'not_authorized' ? denials : [];
      return {
        code,
        typeUri,
        title: meta.title,
        meaning: meta.meaning,
        purposeSlugs,
        demonstratedBy,
        coverage: meta.coverage,
        problemJson: {
          type: typeUri,
          title: meta.title,
          status: meta.status,
          code,
          detail: 'The request was refused. No source rows or out-of-purpose fields were disclosed.'
        }
      } satisfies ProblemCode;
    });
}
