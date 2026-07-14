# Solmara Purpose Catalogue

Status: normative for Solmara Lab wave 1.

All Solmara purpose IRIs are minted under
`https://id.registrystack.org/solmara/purpose/...`. Manifests advertise these
IRIs, notaries enforce these IRIs, and smoke tests assert these IRIs and stable
problem codes. Smoke tests must not assert denial message text.

## Wave 1 Purposes

| Purpose IRI | Advertised by | Enforced by | Story | Denial problem codes |
|---|---|---|---|---|
| `https://id.registrystack.org/solmara/purpose/child-benefit-review` | Civil Registration Authority, National Identity Agency, Social Registry Office, MoSD programme MIS | `child-benefit-federator` plus source-owned child-benefit Notaries | Birth to child benefit | `pdp.purpose_not_permitted`; `federation.forbidden` for delegated calls outside scope |
| `https://id.registrystack.org/solmara/purpose/pension-payment-review` | Civil Registration Authority, Social Insurance and Pensions Fund | `pension-notary` | Death to pension stop | `pdp.purpose_not_permitted`; `federation.forbidden`; `federation.replay` |
| `https://id.registrystack.org/solmara/purpose/survivor-benefit-determination` | Civil Registration Authority, Social Insurance and Pensions Fund | `pension-notary` | Survivor benefit | `pdp.purpose_not_permitted`; `federation.forbidden`; `federation.replay` |
| `https://id.registrystack.org/solmara/purpose/voucher-eligibility-review` | National Agricultural Data Institute | `nagdi-notary` | Farmer climate-smart voucher | `pdp.purpose_not_permitted` |
| `https://id.registrystack.org/solmara/purpose/livestock-movement-control` | National Agricultural Data Institute | `nagdi-notary` | Livestock movement permit companion | `pdp.purpose_not_permitted` |
| `https://id.registrystack.org/solmara/purpose/citizen-self-service` | All wave 1 authorities | `citizen-notary` | Citizen portal | `pdp.purpose_not_permitted`; `federation.forbidden` |

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
| Birth to child benefit | `solmara.child-benefit.federated-predicate-bundle` | Not issued by the federator |
| Death to pension stop | `solmara.pension.payment-stop-review` | `https://id.registrystack.org/solmara/vct/pension-payment-stop-review` |
| Survivor benefit | `solmara.pension.survivor-benefit-eligibility` | `https://id.registrystack.org/solmara/vct/survivor-benefit-eligibility` |
| Farmer climate-smart voucher | `solmara.nagdi.climate-smart-voucher-eligibility` | `https://id.registrystack.org/solmara/vct/climate-smart-voucher-eligibility` |
| Livestock movement permit | `solmara.nagdi.livestock-movement-permit` | `https://id.registrystack.org/solmara/vct/livestock-movement-permit` |

## Denial Assertions

Purpose-denial smoke tests assert:

1. The denied request used a purpose IRI outside the permitted catalogue or a
   permitted purpose against a prohibited field.
2. The response problem code is `pdp.purpose_not_permitted`.
3. The response does not include the prohibited source field.

Federation smoke tests assert:

1. Unsupported delegated purpose returns `federation.forbidden`.
2. Replayed delegated evaluation returns `federation.replay`.
3. Message text is ignored.
