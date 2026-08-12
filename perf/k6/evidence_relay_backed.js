import crypto from 'k6/crypto';
import encoding from 'k6/encoding';
import http from 'k6/http';
import { check } from 'k6';
import {
  EVIDENCE_JWS,
  commonOptions,
  env,
  evidencePayload,
  jsonHeaders,
  parseJson,
  profiledScenario,
  recordStatus,
  requiredEnv,
  sleepIfConfigured,
  summaryFor,
} from './lib/common.js';

const evidenceUrl = env('SOLMARA_EVIDENCE_URL', 'https://localhost:4341');
const evidenceToken = requiredEnv('SOLMARA_EVIDENCE_ACCESS_TOKEN');

const uinSubjects = ['2300010248', '2300091305', '2300036523', '2300073046'];
const farmerSubjects = ['FR-1001', 'FR-1002', 'FR-1003', 'FR-1004'];

export const options = {
  ...commonOptions({
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<1500'],
  }),
  scenarios: {
    evidence_relay_backed: profiledScenario({
      rateDefault: 200,
      preAllocatedVusDefault: 64,
      maxVusDefault: 400,
      stages: [
        { duration: '1m', target: 100 },
        { duration: '1m', target: 200 },
        { duration: '1m', target: 400 },
        { duration: '30s', target: 0 },
      ],
    }),
  },
};

function requestNonce() {
  return encoding.b64encode(crypto.randomBytes(32), 'rawurl');
}

export default function () {
  const cases = [
    {
      name: 'cra_child_benefit',
      subject: uinSubjects[(__VU + __ITER) % uinSubjects.length],
      requirement: 'https://id.registrystack.org/solmara/requirement/cra-child-benefit/v1',
      purpose: 'child-benefit-review',
      profile: 'solmara-uin-v1',
      field: 'uin',
    },
    {
      name: 'cra_death_registration_review',
      subject: uinSubjects[(__VU + __ITER) % uinSubjects.length],
      requirement: 'https://id.registrystack.org/solmara/requirement/cra-pension-death/v1',
      purpose: 'pension-payment-review',
      profile: 'solmara-uin-v1',
      field: 'uin',
    },
    {
      name: 'sipf_pension_payment_review',
      subject: uinSubjects[(__VU + __ITER) % uinSubjects.length],
      requirement: 'https://id.registrystack.org/solmara/requirement/sipf-pension-payment/v1',
      purpose: 'pension-payment-review',
      profile: 'solmara-uin-v1',
      field: 'uin',
    },
    {
      name: 'voucher_eligibility_review',
      subject: farmerSubjects[(__VU + __ITER) % farmerSubjects.length],
      requirement: 'https://id.registrystack.org/solmara/requirement/nagdi-voucher/v1',
      purpose: 'voucher-eligibility-review',
      profile: 'farmer-reference-v1',
      field: 'farmer_id',
    },
  ];
  const item = cases[(__VU + __ITER) % cases.length];
  const response = http.post(
    `${evidenceUrl}/v1/evidence`,
    evidencePayload(
      requestNonce(),
      item.subject,
      item.requirement,
      item.purpose,
      item.profile,
      item.field,
    ),
    { headers: jsonHeaders(evidenceToken, EVIDENCE_JWS) },
  );
  const body = parseJson(response);
  const ok = check(response, {
    [`${item.name} returned 200`]: (r) => r.status === 200,
    [`${item.name} returned a flattened JWS`]: () => (
      typeof body.protected === 'string'
      && typeof body.payload === 'string'
      && typeof body.signature === 'string'
    ),
  });
  recordStatus(ok, response, 200);
  sleepIfConfigured();
}

export const handleSummary = summaryFor('evidence_relay_backed');
