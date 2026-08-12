# Farmer Climate-Smart Voucher

Status: normative for Solmara Lab wave 1 story 3.

## Purpose

This story ports the NAgDI agriculture demo into Solmara. It demonstrates how a
spreadsheet-backed farmer and livestock registry becomes a governed API with
purpose-limited evidence, stable offerings, and smokeable denial behavior.

The livestock movement permit companion ships in the same story package.

## Authorities And Registries

| Authority | Registry | Evidence role |
|---|---|---|
| National Agricultural Data Institute | Farmer registry | Farmer registration, holding, programme, voucher, data-use authorization |
| National Agricultural Data Institute | Livestock registry | Premises, herd, animal, vaccination, quarantine, movement permit |

Purpose IRIs:

- `https://id.registrystack.org/solmara/purpose/voucher-eligibility-review`
- `https://id.registrystack.org/solmara/purpose/livestock-movement-control`

Evidence offerings:

- `solmara.nagdi.climate-smart-voucher-eligibility`
- `solmara.nagdi.livestock-movement-permit`

The active lab bundle permits signed JWS responses for both requirements. It
does not expose a wallet issuance flow for either application decision.

## Positive Path

Persona: Amina Kone, `FR-1001`, legacy alias `FARMER-1001`, Brenholm district.

Expected voucher claims:

| Claim | Expected result |
|---|---|
| `farmer-is-registered` | Pass: Amina has an active `FR-*` farmer record. |
| `data-use-authorized` | Pass: NAgDI has active authorization for voucher review. |
| `holding-in-eligible-district` | Pass: holding district is eligible for the climate-smart package. |
| `not-already-redeemed` | Pass: no redeemed voucher exists for the same programme cycle. |

Expected livestock companion claims:

| Claim | Expected result |
|---|---|
| `movement-applicant-controls-herd` | Pass: Amina controls the herd or premises. |
| `vaccination-current` | Pass: required vaccinations are current for the species. |
| `origin-district-not-quarantined-for-species` | Pass: no species-specific quarantine applies. |
| `destination-permitted` | Pass: destination district allows the movement. |

Registry Evidence calls the NAgDI farmer or herd Records API for the selected
requirement and returns a signed minimized assertion. The voucher requirement
is `https://id.registrystack.org/solmara/requirement/nagdi-voucher/v1`; the
livestock requirement is
`https://id.registrystack.org/solmara/requirement/nagdi-livestock/v1`.
Responses disclose approved concepts, not full workbook rows.

## Failure Cases

| Persona | Case | Expected result |
|---|---|---|
| Diego Santos | Missing data-use authorization | Voucher eligibility fails `data-use-authorized`. |
| Noor Patel | Ineligible climate-risk band | Voucher eligibility fails district or package eligibility without dumping market-sizing cells. |
| Beatriz Okafor | Species-specific quarantine | Livestock movement fails `origin-district-not-quarantined-for-species`. |
| Sefu Dela Cruz | Incomplete vaccination evidence | Livestock movement fails `vaccination-current`. |

## Purpose Denial

The smoke must submit the livestock requirement with the voucher purpose and
the voucher requirement with the livestock purpose. Each mismatch must return
HTTP 403 `not_authorized` before source access. Neither requirement exposes
voucher budget, market-sizing, or unrelated movement details.

## Smoke Expectations

The story smoke asserts:

1. Metadata discovery returns both NAgDI offerings and purpose IRIs from
   `docs/purposes.md`.
2. Amina passes voucher eligibility and receives a verifiable signed Evidence
   assertion.
3. Amina passes the livestock movement companion and receives a verifiable
   signed Evidence assertion.
4. Diego, Noor, Beatriz, and Sefu each fail the listed predicate.
5. Cross-purpose NAgDI access is denied with HTTP 403 `not_authorized`.
6. The ported claim configs use `FR-*` farmer identifiers and Solmara P-coded
   districts, not legacy real-country geography or agriculture national-id
   aliases.
