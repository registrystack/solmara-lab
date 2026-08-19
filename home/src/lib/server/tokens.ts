import { buildPublicUrlMap, mapPublicUrl } from './urlmap';
import type { CurlExample } from '$lib/types';

const CHILD_PURPOSE = 'https://id.registrystack.org/solmara/purpose/child-benefit-review';
const PENSION_PURPOSE = 'https://id.registrystack.org/solmara/purpose/pension-payment-review';

/**
 * Build copyable examples without publishing a credential, identifier, selector
 * value, or nonce. Runtime credentials stay server-side; shell placeholders make
 * the trust boundary visible to engineers.
 */
export function buildCurlExamples(): CurlExample[] {
  const map = buildPublicUrlMap();
  const metadataUrl = mapPublicUrl('http://deterministic-publisher:8080/metadata/catalog.json', map);
  const craUrl = mapPublicUrl('https://cra-evidence.solmara.registrystack.org/v1/evidence', map);
  const niaUrl = mapPublicUrl('https://nia-evidence.solmara.registrystack.org/v1/evidence', map);
  const programmeUrl = mapPublicUrl('http://child-benefit-federator:8080/v1/evaluations', map);
  const craBody = evidenceBody(
    'https://id.registrystack.org/solmara/requirement/cra-child-benefit/v1',
    CHILD_PURPOSE
  );
  const niaBody = evidenceBody(
    'https://id.registrystack.org/solmara/requirement/nia-child-benefit/v1',
    CHILD_PURPOSE
  );

  return [
    {
      id: 'metadata-get',
      title: 'Read the deterministic publication',
      note: 'Published metadata is public. The deterministic publisher is not an Evidence authority.',
      command: `curl -sS '${metadataUrl}'`
    },
    {
      id: 'cra-evidence-post',
      title: 'Ask CRA Evidence for one minimized value',
      note: 'Purpose is a JSON member. Supply the scoped token, nonce, and UIN from your local shell.',
      command: evidenceCurl(craUrl, '$CRA_EVIDENCE_ACCESS_TOKEN', craBody)
    },
    {
      id: 'nia-evidence-post',
      title: 'Ask NIA Evidence independently',
      note: 'CRA and NIA are distinct Evidence services with distinct issuers and audiences.',
      command: evidenceCurl(niaUrl, '$NIA_EVIDENCE_ACCESS_TOKEN', niaBody)
    },
    {
      id: 'programme-post',
      title: 'Run the child-benefit programme collection',
      note: 'The programme sends its governed purpose in the JSON body and collects separately signed authority results.',
      command:
        `curl -sS -X POST '${programmeUrl}' \\\n` +
        `  -H 'x-api-key: $CHILD_BENEFIT_PROGRAMME_TOKEN' \\\n` +
        `  -H 'Content-Type: application/json' \\\n` +
        `  -d '${programmeBody(CHILD_PURPOSE)}'`
    },
    {
      id: 'wrong-purpose-post',
      title: 'Skeptic path: an unapproved JSON purpose',
      note: 'The same requirement under a pension purpose is refused with the current not_authorized problem code.',
      command: evidenceCurl(craUrl, '$CRA_EVIDENCE_ACCESS_TOKEN', evidenceBody(
        'https://id.registrystack.org/solmara/requirement/cra-child-benefit/v1',
        PENSION_PURPOSE
      ))
    }
  ];
}

function evidenceBody(requirement: string, purpose: string): string {
  return JSON.stringify({
    requestNonce: '$REQUEST_NONCE',
    requirement,
    purpose,
    subjects: [{ role: 'subject', selector: { profile: 'solmara-uin-v1', values: { uin: '$SOLMARA_UIN' } } }]
  });
}

function programmeBody(purpose: string): string {
  return JSON.stringify({
    purpose,
    target: {
      type: 'Person',
      identifiers: [{ scheme: 'solmara_uin', value: '$SOLMARA_UIN' }]
    },
    claims: [
      'birth-is-registered',
      'population-record-active',
      'child-age-under-5',
      'household-below-poverty-threshold',
      'not-already-enrolled'
    ],
    disclosure: 'predicate',
    format: 'application/json'
  });
}

function evidenceCurl(url: string, token: string, body: string): string {
  return `curl -sS -X POST '${url}' \\\n  -H 'Authorization: Bearer ${token}' \\\n  -H 'Content-Type: application/json' \\\n  -d '${body}'`;
}
