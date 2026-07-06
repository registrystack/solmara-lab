export type MetadataStatus = 'up' | 'auth-gated' | 'down';

export type StatusItem = {
  id: string;
  label: string;
  href?: string;
  status: MetadataStatus;
  httpStatus?: number;
};

export type Purpose = {
  iri: string;
  slug: string;
  advertisedBy: string;
  enforcedBy: string;
  story: string;
  denialCodes: string[];
  plainLanguage: string;
};

export type StoryStepLink = {
  storyId: string;
  storyTitle: string;
  stepId: string;
  stepLabel: string;
};

export type PurposeView = Purpose & {
  storyLinks: StoryStepLink[];
};

export type ProblemCode = {
  code: string;
  typeUri: string;
  title: string;
  meaning: string;
  purposeSlugs: string[];
  demonstratedBy: StoryStepLink[];
  coverage?: string;
  problemJson: Record<string, unknown>;
};

export type ConfigLink = {
  label: string;
  path: string;
  url: string;
};

export type TopologyService = {
  id: string;
  label: string;
  role: 'shared' | 'relay' | 'notary';
  authority?: string;
  purpose?: string;
  blurb: string;
  config: ConfigLink[];
};

export type TopologyGroup = {
  key: string;
  title: string;
  blurb: string;
  services: TopologyService[];
};

export type SmokeEvidence = {
  available: boolean;
  file?: string;
  timestamp?: string;
  href?: string;
};

export type SeedSummary = {
  available: boolean;
  artifactCount?: number;
  observedAt?: string;
};

export type PublishedToken = {
  name: string;
  token: string;
  purpose?: string;
  note: string;
};

export type CurlExample = {
  id: string;
  title: string;
  note: string;
  command: string;
};

export type Persona = {
  persona_id: string;
  roster_primary_id: string;
  given_name: string;
  family_name: string;
  role: string;
  district_code: string;
};

export type ScenarioStep = {
  id: string;
  label: string;
  prompt: string;
  button: string;
  request_summary: string;
  request_preview?: {
    method: string;
    url: string;
    headers: Record<string, string>;
    body?: unknown;
  };
};

export type Scenario = {
  id: string;
  title: string;
  short_title: string;
  proves: string;
  domain: string;
  actor: string;
  intro: string;
  subject: { name: string; identifier: string };
  requester: { name: string; purpose: string };
  steps: ScenarioStep[];
  receipt: { label: string; value: string }[];
};

export type RequestSource = {
  method: string;
  url: string;
  headers: Record<string, string>;
  body?: unknown;
};

export type ResponseSource = {
  status?: number | null;
  headers?: Record<string, string>;
  body?: unknown;
  error?: string;
  note?: string;
};

export type CredentialSummary = {
  status: 'issued' | 'not_issued' | 'not_attempted';
  profile: string;
  format: string;
  issuer?: string | null;
  credential_id?: string | null;
  expires_at?: string | null;
  holder_id?: string | null;
  disclosures?: number;
  compact_preview?: string | null;
  reason?: string;
  http_status?: number | null;
  message?: string;
};

export type StepRunResult = {
  step_id: string;
  friendly: { title: string; message: string; status: string; facts: { label: string; value: unknown }[] };
  request_source: RequestSource;
  response_source: ResponseSource;
  credential_source?: RequestSource;
  credential_response_source?: ResponseSource;
  credential?: CredentialSummary;
};

export type StepRunEnvelope = {
  schema_version?: string;
  scenario_id?: string;
  result?: StepRunResult;
  error?: string;
};

export type MetadataAuthority = { id: string; name: string; iri?: string };
export type MetadataPublicService = {
  id: string;
  iri?: string;
  competent_authority?: string;
  data_services?: string[];
  title?: Record<string, string>;
  description?: Record<string, string>;
};

export type MetadataBundle = {
  available: boolean;
  error?: string;
  apiCatalog?: Record<string, unknown>;
  catalog: {
    datasets: MetadataDataset[];
    gray_registries: GrayRegistry[];
    authorities: MetadataAuthority[];
    public_services: MetadataPublicService[];
  };
  offerings: MetadataOffering[];
  policies: Record<string, unknown>[];
};

export type MetadataDataset = {
  id: string;
  title: string;
  description: string;
  authority?: { id: string; name: string };
  entities: { name: string; title: string; purposes: string[]; semantics?: { concepts?: string[] } }[];
  purposes: string[];
};

export type MetadataOffering = {
  id: string;
  iri?: string;
  title: string;
  description: string;
  dataset: string;
  entity: string;
  evidence_type: string;
  purposes: string[];
  public_services?: string[];
  lookup_keys?: string[];
  issuing_authority?: { id?: string; name?: string; iri?: string };
  access?: { endpoint_url?: string; discovery_url?: string; kind?: string; ruleset?: string };
  semantics?: { concepts?: string[]; application_profiles?: string[] };
  policy?: string;
};

export type GrayRegistry = {
  id: string;
  title: string;
  owner: string;
  wave: number | null;
};

export type HomeData = {
  metadata: MetadataBundle;
  scenarios: Scenario[];
  defaultScenarioId: string;
  purposes: Purpose[];
  personas: Persona[];
  districts: Record<string, unknown>;
  provinces: Record<string, unknown>;
  country: Record<string, unknown>;
  status: StatusItem[];
  services: string[];
  versions: Record<string, string>;
  smoke: SmokeEvidence;
  seed: SeedSummary;
  publishedTokens: PublishedToken[];
  curlExamples: CurlExample[];
  changelogLatest: ChangelogEntry | null;
  repoUrl: string;
  generatedAt: string;
  portalUrl: string;
};

export type ChangelogEntry = {
  date: string;
  title: string;
  href: string;
};

export type ChangelogFullEntry = {
  date: string;
  title: string;
  body: string;
};

export type StoryStandard = { label: string; note: string };
