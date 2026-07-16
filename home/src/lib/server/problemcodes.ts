import type { ProblemCode, Purpose, Scenario, StoryStepLink } from '$lib/types';

/**
 * Static, maintained metadata for every stable problem code the lab can emit.
 * The `typeUri` values are the problem type URIs actually observed in Notary
 * responses. The set of codes is assembled from the purpose catalogue (which
 * lists each purpose's denial codes) plus these entries, so the page never
 * hand-maintains prose that can drift from the catalogue. Meanings are plain
 * English with the product terms explained inline.
 */
const CODE_META: Record<
  string,
  { title: string; status: number; typeUri: string; meaning: string; coverage?: string }
> = {
  'pdp.purpose_not_permitted': {
    title: 'Purpose not permitted',
    status: 403,
    typeUri: 'https://id.registrystack.org/problems/registry-notary/pdp/purpose_not_permitted',
    meaning:
      'The request named a purpose the authority does not allow for this evidence, or asked for a field outside that purpose. The Notary (the service that certifies evidence) refuses and discloses nothing. This is purpose limitation enforced at request time.'
  },
  'request.invalid': {
    title: 'Invalid evidence request',
    status: 400,
    typeUri: 'https://id.registrystack.org/problems/registry-notary/request/invalid',
    meaning:
      'The request asked for something the Notary will not serve, such as a raw source row instead of a purpose-limited predicate. The Notary rejects the request rather than reach into the register. This is the clean refusal a skeptic gets when they try a raw row read.',
    coverage: 'Asserted by the published-token smoke: a raw-row read attempt with a published demo token.'
  }
};

/** Steps whose id marks them as a purpose denial demonstrate purpose_not_permitted. */
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
        typeUri: `https://id.registrystack.org/problems/registry-notary/${code.replace(/\./g, '/')}`,
        meaning: 'A stable problem code emitted by the stack. See the purpose catalogue for where it applies.'
      };
      const typeUri = meta.typeUri;
      const purposeSlugs = purposes.filter((purpose) => purpose.denialCodes.includes(code)).map((purpose) => purpose.slug);
      const demonstratedBy = code === 'pdp.purpose_not_permitted' ? denials : [];
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
