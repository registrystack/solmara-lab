import http from 'k6/http';
import { check } from 'k6';
import {
  bearerHeaders,
  CHILD_BENEFIT_PURPOSE,
  PENSION_PAYMENT_PURPOSE,
  VOUCHER_PURPOSE,
  commonOptions,
  env,
  profiledScenario,
  recordStatus,
  requiredEnv,
  sleepIfConfigured,
  summaryFor,
} from './lib/common.js';

const civilUrl = env('CIVIL_RELAY_URL', 'http://127.0.0.1:4311');
const populationUrl = env('POPULATION_RELAY_URL', 'http://127.0.0.1:4312');
const socialRegistryUrl = env('SOCIAL_REGISTRY_RELAY_URL', 'http://127.0.0.1:4313');
const programmeUrl = env('PROGRAMME_RELAY_URL', 'http://127.0.0.1:4314');
const pensionsUrl = env('PENSIONS_RELAY_URL', 'http://127.0.0.1:4315');
const nagdiUrl = env('NAGDI_RELAY_URL', 'http://127.0.0.1:4316');

const civilRowToken = requiredEnv('CRA_CHILD_BENEFIT_SOURCE_RAW');
const civilMetadataToken = requiredEnv('CRA_CITIZEN_SOURCE_RAW');
const populationRowToken = requiredEnv('NIA_CHILD_BENEFIT_SOURCE_RAW');
const socialRegistryRowToken = requiredEnv('SRO_CHILD_BENEFIT_SOURCE_RAW');
const programmeRowToken = requiredEnv('PROGRAMME_CHILD_BENEFIT_SOURCE_RAW');
const pensionsRowToken = requiredEnv('SIPF_PENSION_SOURCE_RAW');
const nagdiRowToken = requiredEnv('NAGDI_NOTARY_SOURCE_RAW');

export const options = {
  ...commonOptions({
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<750'],
  }),
  scenarios: {
    relay_stack_read: profiledScenario({
      rateDefault: 1000,
      preAllocatedVusDefault: 256,
      maxVusDefault: 1200,
      stages: [
        { duration: '1m', target: 1000 },
        { duration: '1m', target: 2000 },
        { duration: '1m', target: 5000 },
        { duration: '30s', target: 0 },
      ],
    }),
  },
};

export default function () {
  const routes = [
    {
      name: 'civil_row',
      url: `${civilUrl}/v1/datasets/cra_civil/entities/civil_person/records?id=2300010248&limit=1`,
      token: civilRowToken,
      purpose: CHILD_BENEFIT_PURPOSE,
    },
    {
      name: 'civil_metadata',
      url: `${civilUrl}/metadata/catalog`,
      token: civilMetadataToken,
      purpose: CHILD_BENEFIT_PURPOSE,
    },
    {
      name: 'population_row',
      url: `${populationUrl}/v1/datasets/nia_population/entities/person/records?id=2300010248&limit=1`,
      token: populationRowToken,
      purpose: CHILD_BENEFIT_PURPOSE,
    },
    {
      name: 'social_registry_row',
      url: `${socialRegistryUrl}/v1/datasets/sro_social/entities/household/records?head_uin=2300027390&limit=1`,
      token: socialRegistryRowToken,
      purpose: CHILD_BENEFIT_PURPOSE,
    },
    {
      name: 'programme_row',
      url: `${programmeUrl}/v1/datasets/mosd_programme/entities/enrollment/records?uin=2300010248&limit=1`,
      token: programmeRowToken,
      purpose: CHILD_BENEFIT_PURPOSE,
    },
    {
      name: 'pensions_row',
      url: `${pensionsUrl}/v1/datasets/sipf_pensions/entities/pension_case/records?pensioner_uin=2300109568&limit=1`,
      token: pensionsRowToken,
      purpose: PENSION_PAYMENT_PURPOSE,
    },
    {
      name: 'nagdi_farmer_row',
      url: `${nagdiUrl}/v1/datasets/nagdi_agriculture/entities/farmer_voucher/records?id=FR-1001&limit=1`,
      token: nagdiRowToken,
      purpose: VOUCHER_PURPOSE,
    },
  ];

  const route = routes[(__VU + __ITER) % routes.length];
  const response = http.get(route.url, { headers: bearerHeaders(route.token, route.purpose) });
  const ok = check(response, {
    [`${route.name} returned 200`]: (r) => r.status === 200,
  });
  recordStatus(ok, response, 200);
  sleepIfConfigured();
}

export const handleSummary = summaryFor('relay_stack_read');
