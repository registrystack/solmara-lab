# Solmara purpose catalogue

Status: normative for the authority-owned Evidence reset.

Evidence requests carry one closed purpose code in the signed request body.
For Relay-backed requirements, the Evidence cell authenticates to Registry Mint
with a dedicated private-key JWT client. Mint issues a token whose registration
fixes the full purpose IRI, exact Relay scope, and `solmara-runtime` audience.
The caller cannot select or override downstream Relay authority.

| Purpose code | Authority requirements | Evidence source |
|---|---|---|
| `child-benefit-review` | CRA, NIA, SRO, MoSD | three immutable extracts, one Relay lookup |
| `pension-payment-review` | CRA death, SIPF payment | two Relay lookups |
| `survivor-benefit-determination` | SIPF survivor | Relay lookup |
| `voucher-eligibility-review` | NAgDI voucher | Relay lookup |
| `livestock-movement-control` | NAgDI livestock | Relay lookup |
| `citizen-self-service` | CRA link, NIA status | one Relay lookup, one immutable extract |

Child benefit permits only registered-birth, under-five, active-population,
poverty-priority, and not-already-enrolled concepts. Pension permits death and
active-payment concepts but not cause of death, payment amount, or history.
Survivor review permits the reviewed eligibility value, not a marriage record.
Agriculture purposes are isolated from one another. Citizen self-service permits
only CRA linkage and NIA active-population concepts.

Wrong-purpose or unauthorized requests fail generically. Relay no-match,
ambiguous match, and concealed records collapse to unresolved consultation.
Responses and logs never include selectors, tokens, source rows, secrets,
private keys, audit material, or sensitive dependency details.

The programme application verifies every authority JWS and owns the final
cross-authority outcome. No Evidence cell returns an application decision.
