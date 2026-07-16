# Republic of Solmara

Status: normative for Solmara Lab wave 1.

Solmara is a fictional country created for Registry Stack demonstrations. Any
person, place, ministry, registry, identifier, service, and government story in
this lab is synthetic unless explicitly labelled as an external partner system.
No Solmara address, person, ministry, or registry represents a real authority.

## Nation

The Republic of Solmara is a small cosmopolitan island republic in the tropical
South Indian Ocean, roughly 9.5 to 11 degrees south and 79 to 80.5 degrees east.
It has one main island plus smaller islands, about 24,000 square km, and a
notional population of 2.4 million.

The nearest real land is about 900 km away in every direction, including Diego
Garcia, Addu Atoll, Sri Lanka, and the Cocos Islands. Country-scale basemaps
therefore show open water around Solmara, and no real address should ever fall
inside the lab bounding box.

Solmara uses the ISO 3166 user-assigned codes `XS` and `XSO`. Lab currency uses
the ISO 4217 testing code `XTS`, displayed as the Solmara sol.

## Administrative Areas

Solmara has two administrative levels: 4 provinces and 12 districts. Province
P-codes use `XS-01` through `XS-04`; district P-codes use `XS-0101` style.

| Province code | Province | Position | District code | District |
|---|---|---|---|---|
| `XS-01` | Anvela | North | `XS-0101` | Ketterin |
| `XS-01` | Anvela | North | `XS-0102` | Ovasse |
| `XS-01` | Anvela | North | `XS-0103` | Brenholm |
| `XS-02` | Tolara | South | `XS-0201` | Salvet |
| `XS-02` | Tolara | South | `XS-0202` | Marindi |
| `XS-02` | Tolara | South | `XS-0203` | Velcor |
| `XS-03` | Mendira | Central, capital province | `XS-0301` | Lydessa |
| `XS-03` | Mendira | Central, capital province | `XS-0302` | Orivale |
| `XS-03` | Mendira | Central, capital province | `XS-0303` | Carrowen |
| `XS-04` | Corvala | East | `XS-0401` | Eastmere |
| `XS-04` | Corvala | East | `XS-0402` | Navaro |
| `XS-04` | Corvala | East | `XS-0403` | Vestrel |

These names replace legacy compass districts and any real-country agriculture
geography from the previous NAgDI lab material.

## Coordinate Reference System

The hand-authored Solmara geography uses one hemisphere and one UTM zone. Source
GeoJSON is authored in WGS 84 longitude and latitude (`EPSG:4326`). Metric
derivations for area, centroids, and tiling checks use WGS 84 / UTM zone 44S
(`EPSG:32744`).

The country, provinces, and districts are maintained as one authoritative geo
source. Districts exactly tile provinces, provinces exactly tile the country,
and point fixtures must fall inside their declared district. Relay serves
district geometries only when a story needs boundaries; default story surfaces
prefer names, codes, and minimized predicates.

## Identifier Formats

| Scheme | Format | Example |
|---|---|---|
| SolmaraID UIN | 10 digits, MOSIP-style Verhoeff checksum, no leading 0 or 1, no long runs or repeats, excluding sequences 786 and 666 | `2300010248` |
| Birth registration | `BRN-<year>-<district digits>-<serial>` | `BRN-2016-0101-00213` |
| Death registration | `DRN-<year>-<district digits>-<serial>` | `DRN-2026-0301-00042` |
| Marriage registration | `MRN-<year>-<district digits>-<serial>` | `MRN-1988-0301-00117` |
| Taxpayer | 9 digits plus check letter | `104238756K` |
| Business | org-id style jurisdiction-list code | `XS-SBRS-0042317` |
| Cadastre parcel | `XS-CAD-<district digits>-<serial>` | `XS-CAD-0101-0087` |
| Health facility | `XS-MOH-<serial>` | `XS-MOH-0231` |
| Farmer | `FR-<serial>` | `FR-1001` |
| Household | `HH-<serial>` | `HH-002317` |

Registry-local row-id prefixes are normative when used by the owning registry
model: `CP-`, `BE-`, `DE-`, `ME-`, `MT-`, `CSR-`, `SEP-`, `SCOR-`, `ENR-`,
`ENT-`, `PAY-`, `SIPF-`, `SIPF-AWD-`, `XS-LP-`, `XS-BAU-`, `XS-DLG-`,
`XS-SRA-TCC-`, `XS-DR-`, `XS-SCH-`, `XS-LRN-`, and `XS-MOH-ORG-`.

Legacy national-id aliases remain only for migration and story porting. They
use the old population prefix and are not new primary identifiers.

## Domain Scheme

Solmara uses three domain layers:

| Layer | Pattern | Use |
|---|---|---|
| Story domains | `*.gov.solmara.example` | Fictional ministry and service names in UI copy, docs, fixtures, and tutorials. These do not resolve. |
| Machine identifiers | `https://id.registrystack.org/solmara/...` | Purpose IRIs, credential `vct` values, schema `$id` values, and issuer identifiers. |
| Service endpoints | `<service>.solmara.registrystack.org` | Real TLS endpoints for hosted lab services. |

Notary node identifiers use `did:web` at their authority service host, for
example `did:web:cra-notary.solmara.registrystack.org`. Credential holder
binding uses `did:jwk`.

## Ministries And Registries

Solmara names 17 registries, but only builds registries when a shipped story
needs them. Wave 1 runs seven registries.

| # | Registry | Owner | Tier | Wave |
|---|---|---|---|---|
| 1 | Civil registration: births, deaths, marriages | Ministry of Interior, Civil Registration Authority | Rows, Relay, Notary source | 1 |
| 2 | Population register / national ID | Ministry of Interior, National Identity Agency | Rows, Relay, Notary source | 1 |
| 3 | Social registry: households | Ministry of Social Development, Social Registry Office | Rows, Relay, Notary source | 1 |
| 4 | Integrated beneficiary registry | Ministry of Social Development, programme MISes | Rows, Relay, Notary source | 1 |
| 5 | Pensions / social insurance | Ministry of Labour, Social Insurance and Pensions Fund | Rows, Relay, Notary source | 1 |
| 6 | Farmer registry | Ministry of Agriculture, National Agricultural Data Institute | Rows, Relay, Notary source | 1 |
| 7 | Livestock registry | Ministry of Agriculture, National Agricultural Data Institute | Rows, Relay, Notary source | 1 |
| 8 | Land registry and cadastre | Ministry of Lands and Survey | Rows, Relay, Notary source | 2 |
| 9 | Taxpayer registry | Ministry of Finance, Solmara Revenue Authority | Rows, Relay, Notary source | 2 |
| 10 | Business / company registry | Ministry of Justice and Commerce, Solmara Business Registration Service | Rows, Relay, Notary source | 2 |
| 11 | Beneficial ownership register | Solmara Business Registration Service | Thin fixtures, evidence only | 2 |
| 12 | Disability registry | Ministry of Social Development, Disability Assessment Board | Thin fixtures, evidence only | 3 |
| 13 | Education learner registry | Ministry of Education | Thin fixtures, evidence only | 3 |
| 14 | Health facility registry | Ministry of Health | Thin fixtures, evidence only | 3 |
| 15 | Patient / immunization registry | Ministry of Health | World bible only | None |
| 16 | Vehicle and driving licence registry | Ministry of Transport | World bible only | None |
| 17 | Customs trader registry | Ministry of Finance, Customs Service | World bible only | None |

Wave 1 runs one authority Notary beside each Relay: `cra-notary`, `nia-notary`,
`sro-notary`, `programme-notary`, `sipf-notary`, and `nagdi-notary`. An
authority Notary exposes every reviewed evidence workflow owned by that
authority. It is not duplicated per purpose. The child-benefit orchestration
service composes the four required authority responses but does not own Notary
correctness state or make the final eligibility decision.

## Persona Roster

This roster is the normative named cast for wave 1 docs and smoke expectations.
Identifiers may be regenerated later, but the persona role and expected outcome
must stay stable.

| Persona | Primary id | District | Wave 1 expected outcome |
|---|---|---|---|
| Mateo Santos | `2300010248` | Ketterin | Child benefit positive child: registered birth, active population record, under 5, eligible household, not enrolled. |
| Elena Dela Cruz | `2300018263` | Ketterin | Mateo guardian: may request the source-owned predicate bundle for programme review. |
| Luis Okafor | `2300027390` | Ketterin | Household head for child benefit positive path. |
| Hana Aquino | `2300036523` | Lydessa | Child benefit denied: household above poverty threshold. |
| Priya Mensah | `2300045650` | Lydessa | Guardian for above-threshold child household. |
| Tomas Bello | `2300054788` | Orivale | Child benefit denied: duplicate enrollment already active. |
| Joana Bello | `2300063915` | Orivale | Guardian for duplicate-enrollment control. |
| Karim Kone | `2300073046` | Marindi | Child benefit routed to birth registration first: UIN exists, BRN is null. |
| Aisha Kone | `2300082172` | Marindi | Guardian for unregistered-birth inclusion path. |
| Esteban Cruz | `2300091305` | Velcor | Deceased child-benefit control: eligibility must fail on life status. |
| Miriam Cruz | `2300100431` | Velcor | Guardian for deceased control path. |
| Rafael Nkomo | `2300109568` | Lydessa | Pension positive deceased member: payments should stop. |
| Imani Nkomo | `2300118698` | Lydessa | Survivor benefit positive spouse linked by MRN. |
| Otto Ferreira | `2300127827` | Orivale | Pension stale-data failure: death not yet registered. |
| Lucia Ferreira | `2300136959` | Orivale | Survivor claim waits for death reconciliation. |
| Mina Rahman | `2300146081` | Carrowen | Survivor denied: marriage dissolved. |
| Pavel Rahman | `2300155218` | Carrowen | Deceased former spouse for dissolved-marriage control. |
| Amina Kone | `FR-1001` | Brenholm | Farmer voucher positive path and livestock movement positive owner. |
| Diego Santos | `FR-1002` | Ovasse | Farmer voucher denied: no data-use authorization on file. |
| Noor Patel | `FR-1003` | Navaro | Farmer voucher denied: already redeemed this season. |
| Beatriz Okafor | `FR-1004` | Eastmere | Livestock movement denied: species-specific quarantine. |
| Sefu Dela Cruz | `FR-1005` | Vestrel | Livestock movement denied: incomplete vaccination evidence. |

## Registry Landscape

The wave 1 registry landscape demonstrates cross-registry life-event services:

| Story | Registries | Outcome |
|---|---|---|
| Birth to child benefit | Civil registration, population, social registry, beneficiary registry | Four authority predicate responses composed for programme eligibility review. |
| Death to pension stop plus survivor benefit | Civil registration, population, pensions, beneficiary registry | Stop predicate for the deceased member and survivor eligibility VC for the spouse. |
| Farmer climate-smart voucher and livestock movement | Farmer registry, livestock registry | Voucher eligibility credential and livestock movement permit evidence. |

Every wave 1 story must show metadata discovery, governed evaluation, a
credential or composed evidence moment, a forbidden raw read or wrong-purpose
attempt, and a denial with a stable problem code.
