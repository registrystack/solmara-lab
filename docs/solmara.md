# Solmara lab architecture

Solmara is a fictional institutional lab. Its core boundary is the authority:
each one publishes a governed source, operates its own Evidence gateway, signs
its assertions, and owns its audit trail. A programme consumes assertions from
several authorities and owns the programme decision.

## Runtime topology

| Authority | Evidence source | Relay operation |
|---|---|---|
| CRA | immutable birth extract | civil death and citizen-link exact lookups |
| NIA | immutable population extract | eSignet UserInfo exact lookup |
| SRO | immutable poverty extract | none |
| MoSD Programme MIS | live read-only SQLite | beneficiary enrolment exact lookup |
| SIPF | live read-only SQLite | pension payment and survivor exact lookups |
| NAgDI | live read-only SQLite | voucher and livestock exact lookups |

There are six Evidence gateways and five Relays. A Relay exists only for
governed live consultation. It is not a façade over an Evidence gateway's
immutable local extract.

Every Relay operation has one dedicated Mint client registration, exact scope,
fixed purpose claim, access profile, and disclosure profile. Relays do not
offer list, search, cursor, or generic record routes. The shared
`solmara-runtime` audience is deliberately limited to this lab.

## Evidence authority

Each gateway has a unique provider IRI, authority DID issuer, ES256 signing key
and JWKS, audit destination, subject-binding secret, runtime binding, and
hostname. The application chooses the gateway from a closed requirement
directory, fetches only that gateway's JWKS, verifies the exact requirement,
evidence type, concepts,
purpose, nonce, issuer, provider, audience, and validity window, then retains a
safe presentation projection.

Direct-source assertions are labelled `immutable extract` and remain valid for
at most 3,600 seconds. Relay-backed assertions are labelled `Relay lookup` and
remain valid for at most 300 seconds. Source rows, selectors, tokens, JWS
payloads, private audit output, and sensitive dependency errors are never UI
presentation data.

## Source publication

Authority publishers produce five mutable Relay databases and three immutable
Evidence extracts. Each extract contains exactly one `evidence_extract` row
with `published_at`, `publisher`, and `extract_id`. A publication is written
under a new name and made read-only. Active extracts are never overwritten.

Relay views expose authority-owned stable record identifiers, revisions,
lifecycle state, recorded timestamps, selector columns, and governed domain
columns. Relay releases only the properties declared by the selected disclosure
profile.

## Failure semantics

Wrong scope, wrong purpose, malformed selectors, invalid source rows,
unavailable source, and unavailable audit fail closed. No-match, ambiguous
match, and policy-hidden matches use the same data-free unresolved class. An
Evidence gateway does not infer a negative assertion from an unresolved Relay
consultation.

## Programme stories

- Child benefit composes CRA, NIA, SRO, and MoSD assertions into five reviewed
  concepts.
- Pension composes CRA death and SIPF payment assertions. SIPF survivor evidence
  is separately requested for the spouse.
- Agriculture requests NAgDI voucher or livestock assertions under isolated
  purposes.
- Optional citizen login uses the NIA Relay V2 lookup through eSignet, while the
  application can separately compose CRA and NIA Evidence assertions.

The preserved `/v1` suffixes in requirement and evidence-type identifiers are
domain identifier versions, not transport routes.
