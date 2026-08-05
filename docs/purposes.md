# Solmara Purpose Catalogue

Status: normative for the local Registry Evidence deployment.

Registry Evidence requests use the closed purpose codes below. The reviewed
source adapters translate those grants into fixed `Data-Purpose` IRIs when they
call each authority's Records API. A caller cannot supply or override those
downstream headers.

## Wave 1 Purposes

| Purpose code | Advertised by | Enforced by | Story | Denial problem codes |
|---|---|---|---|---|
| `child-benefit-review` | Civil Registration Authority, National Identity Agency, Social Registry Office, MoSD programme MIS | Registry Evidence grants and four reviewed requirements | Birth to child benefit | `not_authorized` |
| `pension-payment-review` | Civil Registration Authority, Social Insurance and Pensions Fund | Registry Evidence grants and CRA/SIPF requirements | Death to pension stop | `not_authorized` |
| `survivor-benefit-determination` | Social Insurance and Pensions Fund | Registry Evidence grant and SIPF survivor requirement | Survivor benefit | `not_authorized` |
| `voucher-eligibility-review` | National Agricultural Data Institute | Registry Evidence grant and NAgDI voucher requirement | Farmer climate-smart voucher | `not_authorized` |
| `livestock-movement-control` | National Agricultural Data Institute | Registry Evidence grant and NAgDI livestock requirement | Livestock movement permit companion | `not_authorized` |
| `citizen-self-service` | Civil Registration Authority and National Identity Agency | Registry Evidence grants and CRA/NIA citizen requirements | Citizen portal | `not_authorized` |

## Purpose Rules

`child-benefit-review` permits evidence needed to determine whether a child may
be enrolled in child support: registered birth, age under five, active
population record, household priority band, and duplicate enrollment status.
It does not permit raw poverty scores, complete household profiles, or unrelated
civil events.

`pension-payment-review` permits an application to combine the fact of death
with an active-payment value. It does not permit cause of death, medical detail,
payment amount, or payment history.

`survivor-benefit-determination` permits the reviewed survivor eligibility
value. It does not permit a complete marriage record, contribution history, or
unrelated benefits.

`voucher-eligibility-review` permits farmer registration, data-use
authorization, and voucher eligibility values. It does not permit workbook rows,
unrelated livestock movements, or raw market-sizing data.

`livestock-movement-control` permits registered-herd, quarantine, and movement
eligibility values. It does not permit voucher budgets, crop records, or
household poverty data.

`citizen-self-service` permits separate CRA linkage and NIA active-population
values for the selected persona. It does not permit bulk reads,
administrative-only fields, or evidence for another selected persona.

## Evidence Outputs

| Story | Registry Evidence requirements | Output |
|---|---|---|
| Birth to child benefit | CRA, NIA, SRO, and MoSD child-benefit requirements | Four flattened signed JWS assertions collected by the application |
| Death to pension stop | CRA death and SIPF active-payment requirements | Two flattened signed JWS assertions and an application-owned stop decision |
| Survivor benefit | SIPF survivor requirement | One flattened signed JWS assertion |
| Farmer climate-smart voucher | NAgDI voucher requirement | One flattened signed JWS assertion |
| Livestock movement permit | NAgDI livestock requirement | One flattened signed JWS assertion |
| Citizen self-service | CRA and NIA citizen requirements | Two flattened signed JWS assertions |

## Denial Assertions

Purpose-denial tests assert:

1. The request names a purpose not granted for the selected requirement.
2. Registry Evidence returns HTTP 403 and `not_authorized`.
3. No source row or prohibited field appears in the response.

The child-benefit collector proves that one application can collect four
independently governed signed assertions without owning a shared eligibility
rule or copying authority rows.
