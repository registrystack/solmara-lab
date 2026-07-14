# Solmara Purpose Catalogue

Status: normative for Solmara Lab wave 1.

All Solmara purpose IRIs are minted under
`https://id.registrystack.org/solmara/purpose/...`. Manifests advertise these
IRIs, notaries enforce these IRIs, and smoke tests assert these IRIs and stable
problem codes. Smoke tests must not assert denial message text.

## Wave 1 Purposes

| Purpose IRI | Advertised by | Enforced by | Story | Denial problem codes |
|---|---|---|---|---|
| `https://id.registrystack.org/solmara/purpose/child-benefit-review` | Civil Registration Authority, National Identity Agency, Social Registry Office, MoSD programme MIS | CRA, NIA, SRO, and Programme authority Notaries | Birth to child benefit | `pdp.purpose_not_permitted` |
| `https://id.registrystack.org/solmara/purpose/pension-payment-review` | Civil Registration Authority, Social Insurance and Pensions Fund | CRA and SIPF authority Notaries | Death to pension stop | `pdp.purpose_not_permitted` |
| `https://id.registrystack.org/solmara/purpose/survivor-benefit-determination` | Social Insurance and Pensions Fund | SIPF authority Notary | Survivor benefit | `pdp.purpose_not_permitted` |
| `https://id.registrystack.org/solmara/purpose/voucher-eligibility-review` | National Agricultural Data Institute | NAgDI authority Notary | Farmer climate-smart voucher | `pdp.purpose_not_permitted` |
| `https://id.registrystack.org/solmara/purpose/livestock-movement-control` | National Agricultural Data Institute | NAgDI authority Notary | Livestock movement permit companion | `pdp.purpose_not_permitted` |
| `https://id.registrystack.org/solmara/purpose/citizen-self-service` | Civil Registration Authority and National Identity Agency | CRA and NIA authority Notaries | Citizen portal | `pdp.purpose_not_permitted` |

The two NAgDI purpose identifiers are canonical for wave 1 docs. WP4 must still
confirm that the ported NAgDI claim configs use these exact identifiers.

## Purpose Rules

`child-benefit-review` permits evidence needed to determine whether a child may
be enrolled in child support: registered birth, age under 5, child life status,
household eligibility band, and duplicate enrollment status. It does not permit
raw poverty scores, complete household profiles, or unrelated civil events.

`pension-payment-review` permits the SIPF to determine whether an active pension
payment should continue, be held, or stop. It permits the fact of death and the
death registration number where needed. It does not permit cause of death or
medical details.

`survivor-benefit-determination` permits the SIPF to determine whether a linked
spouse or dependent qualifies for survivor benefits. It permits spouse linkage,
marriage status, death fact, and pension membership predicates. It does not
permit cause of death, complete contribution history, or unrelated benefits.

`voucher-eligibility-review` permits NAgDI to evaluate farmer registration,
data-use authorization, eligible crop or holding records, district risk band,
and prior voucher status. It does not permit unrelated livestock movements or
raw market-sizing tables.

`livestock-movement-control` permits NAgDI to evaluate owner, animal, premises,
vaccination, quarantine, and movement predicates for a livestock permit. It does
not permit farmer voucher budget, unrelated crop records, or household poverty
data.

`citizen-self-service` permits the citizen portal to request preview evidence
for the selected persona and to show proof traces for consented service
journeys. It does not permit bulk reads, administrative-only fields, or evidence
for a different selected persona.

## Credential And Offering Names

| Story | Evidence offering | Credential `vct` |
|---|---|---|
| Birth to child benefit | Four authority predicate responses composed by the child-benefit orchestration service | No credential issued |
| Death to pension stop | `cra-pension-death` and `sipf-pension-payment-review` | No credential issued |
| Survivor benefit | `sipf-survivor-benefit` | `https://id.registrystack.org/solmara/vct/survivor-benefit-status` |
| Farmer climate-smart voucher | NAgDI `voucher` | `https://id.registrystack.org/solmara/vct/climate-smart-voucher-eligibility` |
| Livestock movement permit | NAgDI `livestock` | `https://id.registrystack.org/solmara/vct/livestock-movement-permit` |

## Denial Assertions

Purpose-denial smoke tests assert:

1. The denied request used a purpose IRI outside the permitted catalogue or a
   permitted purpose against a prohibited field.
2. The response problem code is `pdp.purpose_not_permitted`.
3. The response does not include the prohibited source field.

The child-benefit orchestration smoke verifies that four independently governed
authority responses can be composed without creating a seventh Notary or a
shared correctness-state owner.
