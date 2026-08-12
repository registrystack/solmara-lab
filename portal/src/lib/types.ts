// Provenance kinds -> field types (portal spec section 5.3, UX section 3).
export type FieldKind = 'self' | 'verify' | 'fetch' | 'decision';
export type AuthorityId =
  | 'civil'
  | 'social'
  | 'agri'
  | 'certs'
  | 'childCivil'
  | 'population'
  | 'socialRegistry'
  | 'programme';

// Lifecycle state of an EvidenceField (UX section 4 + Phase 0 DoD).
export type FieldState =
  | 'idle'        // self-entry, empty input
  | 'prefilled'   // self identity from eSignet, locked
  | 'in_flight'   // request issued, authority named
  | 'slow'        // > ~6-8s, elapsed counter, "it's a live call"
  | 'verified'    // predicate true (GREEN)
  | 'false'       // predicate false, still signed (AMBER)
  | 'fetched'     // value/object fetched + locked (BLUE)
  | 'stale'       // fetched but older than the freshness rule (BLUE + AMBER flag)
  | 'recovered'   // a retry succeeded
  | 'error'       // authority unreachable; scoped to the field, never full-screen
  | 'ambiguous';  // more than one record matched; never collapses to false

export type Field = {
  id: string;
  label: string;
  kind: FieldKind;
  claim?: string;            // e.g. 'household-below-poverty-threshold'
  authority?: AuthorityId;
  purpose?: string;          // declared purpose, shown in the proof inspector
  disclose?: string;         // what is NOT disclosed (the minimization "money shot")
  selfPlaceholder?: string;  // placeholder for kind:'self' inputs
  manual?: boolean;          // the single climax button (combined-eligibility decision)
  delegated?: { relationshipClaim: string; dependentRef: 'selected-child' };
};

export type ServiceForm = {
  slug: string;
  title: string;
  authorities: AuthorityId[]; // seal glyphs shown on the card / form header
  fields: Field[];
};

// ---- Portal-facing shapes ----
// Raw requests, source rows, bearer tokens, and signed JWS segments remain on
// the server. The browser receives only this bounded presentation projection.

export type ClaimResult = {
  state: FieldState;
  display: string;        // value or predicate sentence shown in the field
  authority?: AuthorityId;
  asOf?: string;          // freshness timestamp
  reasonCode?: string;    // e.g. 'VR-RED-02'
  traceId: string;        // links to the ProofTrace ('event N')
};

export type ProofStatus = 'in_flight' | 'ok' | 'false' | 'denied' | 'error';

export type EvidenceSource = 'immutable extract' | 'Relay lookup';

export type EvidencePresentation = {
  authority: string;
  issuer: string;
  serviceId: string;
  source: EvidenceSource;
};

export type ProofTrace = {
  id: string;             // 'event N' label
  seq: number;
  fieldId?: string;
  authority?: AuthorityId;
  // depth 1 - human
  headline: string;       // consequence-first
  answered: string;       // "{Authority} answered: {claim} = {value}"
  notDisclosed: string;   // ALWAYS present
  status: ProofStatus;
  ts: string;
  purpose?: string;
  resultState: FieldState;
  presentations: EvidencePresentation[];
  responseStatus?: number;
  // Depth 2 is deliberately descriptive. Cryptographic bytes and internal event ids do
  // not cross the BFF boundary.
  proof?: {
    signedBy: string;
    algorithm: string;
    issuerKey: string;
    holderBound: string;
    credential: string;
  };
};

// A rail channel event the ministry constellation animates.
export type RailChannel = 'verify' | 'fetch' | 'denied';
export type RailEvent = {
  id: string;
  authority: AuthorityId;
  channel: RailChannel;
  phase: 'request' | 'sealed' | 'denied';
  ts: string;
};
