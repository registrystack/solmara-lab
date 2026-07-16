import http from 'k6/http';
import { check } from 'k6';
import {
  CLAIM_RESULT,
  CHILD_BENEFIT_PURPOSE,
  PENSION_PAYMENT_PURPOSE,
  VOUCHER_PURPOSE,
  commonOptions,
  env,
  evaluationPayload,
  jsonHeaders,
  parseJson,
  profiledScenario,
  recordStatus,
  requiredEnv,
  sleepIfConfigured,
  summaryFor,
} from './lib/common.js';

const childBenefitFederatorUrl = env('CHILD_BENEFIT_FEDERATOR_URL', 'http://127.0.0.1:4321');
const craNotaryUrl = env('CRA_NOTARY_URL', 'http://127.0.0.1:4325');
const sipfNotaryUrl = env('SIPF_NOTARY_URL', 'http://127.0.0.1:4322');
const nagdiNotaryUrl = env('NAGDI_NOTARY_URL', 'http://127.0.0.1:4323');
const childBenefitToken = requiredEnv('CHILD_BENEFIT_FEDERATOR_TOKEN');
const craPensionToken = requiredEnv('CRA_PENSION_CLIENT_TOKEN');
const sipfPensionToken = requiredEnv('SIPF_PENSION_CLIENT_TOKEN');
const nagdiToken = requiredEnv('NAGDI_NOTARY_TOKEN');

const uinSubjects = ['2300010248', '2300091305', '2300036523', '2300073046'];
const farmerSubjects = ['FR-1001', 'FR-1002', 'FR-1003', 'FR-1004'];

export const options = {
  ...commonOptions({
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<1500'],
  }),
  scenarios: {
    notary_relay_backed: profiledScenario({
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

export default function () {
  const cases = [
    {
      name: 'child_benefit_review',
      url: `${childBenefitFederatorUrl}/v1/evaluations`,
      token: childBenefitToken,
      subject: uinSubjects[(__VU + __ITER) % uinSubjects.length],
      scheme: 'solmara_uin',
      purpose: CHILD_BENEFIT_PURPOSE,
      claim: 'birth-is-registered',
      format: 'application/json',
    },
    {
      name: 'cra_death_registration_review',
      url: `${craNotaryUrl}/v1/evaluations`,
      token: craPensionToken,
      subject: uinSubjects[(__VU + __ITER) % uinSubjects.length],
      scheme: 'solmara_uin',
      purpose: PENSION_PAYMENT_PURPOSE,
      claim: 'person-is-deceased',
      format: CLAIM_RESULT,
    },
    {
      name: 'sipf_pension_payment_review',
      url: `${sipfNotaryUrl}/v1/evaluations`,
      token: sipfPensionToken,
      subject: uinSubjects[(__VU + __ITER) % uinSubjects.length],
      scheme: 'solmara_uin',
      purpose: PENSION_PAYMENT_PURPOSE,
      claim: 'pension-payment-active',
      format: CLAIM_RESULT,
    },
    {
      name: 'voucher_eligibility_review',
      url: `${nagdiNotaryUrl}/v1/evaluations`,
      token: nagdiToken,
      subject: farmerSubjects[(__VU + __ITER) % farmerSubjects.length],
      scheme: 'farmer_id',
      purpose: VOUCHER_PURPOSE,
      claim: 'eligible-for-climate-smart-input-voucher',
      format: CLAIM_RESULT,
    },
  ];
  const item = cases[(__VU + __ITER) % cases.length];
  const response = http.post(
    item.url,
    evaluationPayload(item.subject, item.claim, 'predicate', item.format, item.scheme),
    { headers: jsonHeaders(item.token, item.purpose, item.format) },
  );
  const body = parseJson(response);
  const ok = check(response, {
    [`${item.name} returned 200`]: (r) => r.status === 200,
    [`${item.name} returned results`]: () => Array.isArray(body.results) && body.results.length > 0,
  });
  recordStatus(ok, response, 200);
  sleepIfConfigured();
}

export const handleSummary = summaryFor('notary_relay_backed');
