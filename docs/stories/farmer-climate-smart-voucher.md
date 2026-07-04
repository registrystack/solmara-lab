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

Credential `vct` values:

- `https://id.registrystack.org/solmara/vct/climate-smart-voucher-eligibility`
- `https://id.registrystack.org/solmara/vct/livestock-movement-permit`

Credential names:

- Climate-Smart Voucher Eligibility SD-JWT VC.
- Livestock Movement Permit SD-JWT VC.

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

The NAgDI notary previews or issues the voucher eligibility credential and the
livestock movement permit credential. Responses disclose predicates and
references, not full workbook rows.

## Failure Cases

| Persona | Case | Expected result |
|---|---|---|
| Diego Santos | Missing data-use authorization | Voucher eligibility fails `data-use-authorized`. |
| Noor Patel | Ineligible climate-risk band | Voucher eligibility fails district or package eligibility without dumping market-sizing cells. |
| Beatriz Okafor | Species-specific quarantine | Livestock movement fails `origin-district-not-quarantined-for-species`. |
| Sefu Dela Cruz | Incomplete vaccination evidence | Livestock movement fails `vaccination-current`. |

## Purpose Denial

The smoke must attempt to use `livestock-movement-control` to read voucher
budget, market-sizing, or crop programme details. The response must deny access
with `pdp.purpose_not_permitted`.

The smoke must attempt to use `voucher-eligibility-review` to read unrelated
livestock movement details. The response must deny access with
`pdp.purpose_not_permitted`.

## Smoke Expectations

The story smoke asserts:

1. Metadata discovery returns both NAgDI offerings and purpose IRIs from
   `docs/purposes.md`.
2. Amina passes voucher eligibility and receives the expected voucher `vct`.
3. Amina passes the livestock movement companion and receives the expected
   livestock movement `vct`.
4. Diego, Noor, Beatriz, and Sefu each fail the listed predicate.
5. Cross-purpose NAgDI access is denied with `pdp.purpose_not_permitted`.
6. The ported claim configs use `FR-*` farmer identifiers and Solmara P-coded
   districts, not legacy real-country geography or agriculture national-id
   aliases.
