import { env } from '$env/dynamic/private';
import type { ConfigLink, TopologyGroup, TopologyService } from '$lib/types';

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

const shared = (
  service: Omit<ServiceDef, 'role' | 'semantics'> & { semantics?: ServiceStatusSemantics }
): ServiceDef => ({ ...service, role: 'shared', semantics: service.semantics ?? 'health' });

const relay = (service: Omit<ServiceDef, 'role' | 'semantics'>): ServiceDef => ({
  ...service,
  role: 'relay',
  semantics: 'auth-gated'
});

const evidence = (service: Omit<ServiceDef, 'role' | 'semantics'>): ServiceDef => ({
  ...service,
  role: 'evidence',
  semantics: 'health'
});

export const SERVICES: ServiceDef[] = [
  shared({
    id: 'deterministic-publisher',
    label: 'Deterministic publisher',
    blurb: 'Builds the metadata publication, immutable Evidence extracts, and Relay SQLite sources from one reviewed synthetic input set.',
    probeEnv: 'STATIC_METADATA_URL',
    probeDefault: 'http://127.0.0.1:4331',
    probePath: '/.well-known/api-catalog',
    browsable: true,
    configPaths: [
      { label: 'Publisher', path: 'generator/solmara_lab/publisher.py' },
      { label: 'Published metadata', path: 'metadata/public' },
      { label: 'Generated SQLite outputs', path: 'output/sqlite' }
    ]
  }),
  relay({
    id: 'cra-relay',
    label: 'CRA Relay',
    authority: 'Civil Registration Authority',
    blurb: 'Relay V2 exact lookups over the CRA civil source.',
    probeEnv: 'CRA_CIVIL_RELAY_URL',
    probeDefault: 'http://127.0.0.1:4311',
    probePath: '/ready',
    configPaths: [{ label: 'Relay V2 project', path: 'relays/cra' }]
  }),
  relay({
    id: 'nia-relay',
    label: 'NIA Relay',
    authority: 'National Identity Agency',
    blurb: 'Relay V2 exact lookups over the population source, also available to the optional eSignet path.',
    probeEnv: 'NIA_POPULATION_RELAY_URL',
    probeDefault: 'http://127.0.0.1:4312',
    probePath: '/ready',
    configPaths: [{ label: 'Relay V2 project', path: 'relays/nia' }]
  }),
  relay({
    id: 'mosd-relay',
    label: 'MoSD Programme Relay',
    authority: 'Ministry of Social Development Programme MIS',
    blurb: 'Relay V2 exact lookups over the programme-owned beneficiary enrolment source.',
    probeEnv: 'MOSD_PROGRAMME_RELAY_URL',
    probeDefault: 'http://127.0.0.1:4314',
    probePath: '/ready',
    configPaths: [{ label: 'Relay V2 project', path: 'relays/mosd' }]
  }),
  relay({
    id: 'sipf-relay',
    label: 'SIPF Relay',
    authority: 'Social Insurance and Pensions Fund',
    blurb: 'Relay V2 exact lookups over pension payment and survivor resources.',
    probeEnv: 'SIPF_PENSIONS_RELAY_URL',
    probeDefault: 'http://127.0.0.1:4315',
    probePath: '/ready',
    configPaths: [{ label: 'Relay V2 project', path: 'relays/sipf' }]
  }),
  relay({
    id: 'nagdi-relay',
    label: 'NAgDI Relay',
    authority: 'National Agricultural Data Institute',
    blurb: 'Relay V2 exact lookups over farmer voucher and livestock movement resources.',
    probeEnv: 'NAGDI_AGRICULTURE_RELAY_URL',
    probeDefault: 'http://127.0.0.1:4316',
    probePath: '/ready',
    configPaths: [{ label: 'Relay V2 project', path: 'relays/nagdi' }]
  }),
  evidence({
    id: 'cra-evidence',
    label: 'CRA Evidence',
    authority: 'Civil Registration Authority',
    blurb: 'Issues CRA-signed minimized values from reviewed immutable extracts or CRA Relay lookups.',
    probeEnv: 'SOLMARA_CRA_EVIDENCE_URL',
    probeDefault: 'https://cra-evidence.solmara.registrystack.org',
    probePath: '/health',
    configPaths: [{ label: 'Authority Evidence gateway', path: 'evidence/cells/cra' }]
  }),
  evidence({
    id: 'nia-evidence',
    label: 'NIA Evidence',
    authority: 'National Identity Agency',
    blurb: 'Issues NIA-signed population status values.',
    probeEnv: 'SOLMARA_NIA_EVIDENCE_URL',
    probeDefault: 'https://nia-evidence.solmara.registrystack.org',
    probePath: '/health',
    configPaths: [{ label: 'Authority Evidence gateway', path: 'evidence/cells/nia' }]
  }),
  evidence({
    id: 'sro-evidence',
    label: 'SRO Evidence',
    authority: 'Social Registry Office',
    blurb: 'Issues SRO-signed household poverty values from its immutable extract.',
    probeEnv: 'SOLMARA_SRO_EVIDENCE_URL',
    probeDefault: 'https://sro-evidence.solmara.registrystack.org',
    probePath: '/health',
    configPaths: [{ label: 'Authority Evidence gateway', path: 'evidence/cells/sro' }]
  }),
  evidence({
    id: 'mosd-programme-evidence',
    label: 'MoSD Programme Evidence',
    authority: 'Ministry of Social Development Programme MIS',
    blurb: 'Issues programme-owned duplicate-enrolment values through the social development Relay.',
    probeEnv: 'SOLMARA_MOSD_PROGRAMME_EVIDENCE_URL',
    probeDefault: 'https://mosd-programme-evidence.solmara.registrystack.org',
    probePath: '/health',
    configPaths: [{ label: 'Authority Evidence gateway', path: 'evidence/cells/mosd-programme' }]
  }),
  evidence({
    id: 'sipf-evidence',
    label: 'SIPF Evidence',
    authority: 'Social Insurance and Pensions Fund',
    blurb: 'Issues SIPF-signed pension and survivor values.',
    probeEnv: 'SOLMARA_SIPF_EVIDENCE_URL',
    probeDefault: 'https://sipf-evidence.solmara.registrystack.org',
    probePath: '/health',
    configPaths: [{ label: 'Authority Evidence gateway', path: 'evidence/cells/sipf' }]
  }),
  evidence({
    id: 'nagdi-evidence',
    label: 'NAgDI Evidence',
    authority: 'National Agricultural Data Institute',
    blurb: 'Issues NAgDI-signed voucher and livestock movement values.',
    probeEnv: 'SOLMARA_NAGDI_EVIDENCE_URL',
    probeDefault: 'https://nagdi-evidence.solmara.registrystack.org',
    probePath: '/health',
    configPaths: [{ label: 'Authority Evidence gateway', path: 'evidence/cells/nagdi' }]
  }),
  shared({
    id: 'lab-mint',
    label: 'Shared lab Mint',
    blurb: 'Issues short-lived, audience-bound machine tokens for the six authority Evidence gateways and five Relays.',
    probeEnv: 'MINT_URL',
    probeDefault: 'https://localhost:4341',
    probePath: '/health',
    configPaths: [{ label: 'Mint config', path: 'evidence/mint.yaml' }]
  }),
  shared({
    id: 'child-benefit-programme',
    label: 'Child benefit programme app',
    purpose: 'child-benefit-review',
    blurb: 'Collects separately signed authority Evidence and makes the programme decision. It does not own registry facts.',
    probeEnv: 'CHILD_BENEFIT_FEDERATOR_URL',
    probeDefault: 'http://127.0.0.1:4321',
    probePath: '/health',
    configPaths: [{ label: 'Programme application', path: 'scenario-runner/child_benefit_federator.py' }]
  }),
  shared({
    id: 'scenario-runner',
    label: 'Scenario runner',
    blurb: 'Runs the guided stories against the authority Evidence endpoints.',
    probeEnv: 'SCENARIO_RUNNER_URL',
    probeDefault: 'http://127.0.0.1:4302',
    probePath: '/health',
    configPaths: [{ label: 'Scenario modules', path: 'scenarios' }]
  }),
  shared({
    id: 'esignet',
    label: 'Optional eSignet',
    authority: 'National Identity Agency',
    blurb: 'Optional resident sign-in. It resolves identity through the NIA Relay and is not an Evidence authority.',
    configPaths: [{ label: 'Portal eSignet integration', path: 'portal/src/lib/server/esignet.ts' }]
  }),
  shared({
    id: 'portal',
    label: 'Citizen portal',
    blurb: 'The resident application that presents authority Evidence without exposing selectors or raw wire material.',
    probeEnv: 'PORTAL_PROBE_URL',
    probeDefault: 'http://127.0.0.1:4300',
    probePath: '/',
    browsable: true,
    configPaths: [{ label: 'Portal app', path: 'portal' }]
  }),
  shared({
    id: 'home',
    label: 'Solmara Lab Visitor Center',
    blurb: 'The out-of-fiction front door to the synthetic country.',
    self: true,
    browsable: true,
    configPaths: [{ label: 'Home app', path: 'home' }]
  })
];

export type StatusProbe = {
  id: string;
  label: string;
  role: ServiceRole;
  self: boolean;
  probeUrl?: string;
  href?: string;
};

export function statusProbes(
  portalUrl: string,
  readEnv: Record<string, string | undefined> = env
): StatusProbe[] {
  return SERVICES.map((service) => {
    const base = service.probeEnv ? readEnv[service.probeEnv] ?? service.probeDefault : undefined;
    const probeUrl = base && service.probePath ? joinUrl(base, service.probePath) : undefined;
    let href: string | undefined;
    if (service.browsable) {
      if (service.id === 'deterministic-publisher') href = '/.well-known/api-catalog';
      else if (service.id === 'portal') href = portalUrl;
      else if (service.id === 'home') href = '/';
    }
    return {
      id: service.id,
      label: service.label,
      role: service.role,
      self: Boolean(service.self),
      probeUrl,
      href
    };
  });
}

export function topologyGroups(repoUrl: string): TopologyGroup[] {
  const byId = (ids: string[]) => ids.map((id) => {
    const service = SERVICES.find((candidate) => candidate.id === id);
    if (!service) throw new Error(`Unknown topology service: ${id}`);
    return toTopologyService(service, repoUrl);
  });
  return [
    {
      key: 'publisher',
      title: 'Deterministic publisher',
      blurb: 'One reviewed synthetic input produces public metadata, authority-owned immutable extracts, and Relay SQLite sources deterministically.',
      services: byId(['deterministic-publisher'])
    },
    {
      key: 'relays',
      title: 'Five Relay V2 projects',
      blurb: 'Each live source is exposed through bounded, purpose-protected exact lookups. Direct-only SRO evidence has no Relay.',
      services: byId(['cra-relay', 'nia-relay', 'mosd-relay', 'sipf-relay', 'nagdi-relay'])
    },
    {
      key: 'evidence',
      title: 'Six authority Evidence gateways',
      blurb: 'Each authority has its own Evidence service identity, issuer, reviewed requirements, and origin. The lab Mint is shared infrastructure, never the evidence issuer.',
      services: byId(['cra-evidence', 'nia-evidence', 'sro-evidence', 'mosd-programme-evidence', 'sipf-evidence', 'nagdi-evidence', 'lab-mint'])
    },
    {
      key: 'programme',
      title: 'Programme and visitor applications',
      blurb: 'The child benefit app combines signed authority values into a programme decision. The scenario runner, portal, and Visitor Center present the result.',
      services: byId(['child-benefit-programme', 'scenario-runner', 'portal', 'home'])
    },
    {
      key: 'identity',
      title: 'Optional resident identity',
      blurb: 'eSignet is optional and uses the NIA Relay for identity resolution. It is not a national Evidence service.',
      services: byId(['esignet'])
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
