# Birth To Child Benefit

Status: normative for Solmara Lab wave 1 story 1.

## Purpose

This story demonstrates a canonical CRVS-to-social-protection journey: a
registered birth, a population identity, a household eligibility predicate, and
a programme duplicate check are gathered as signed, source-owned Evidence
assertions without exposing raw registry rows. The programme policy layer, not
Registry Evidence, decides whether those assertions amount to child benefit
eligibility.

## Authorities And Registries

| Authority | Registry | Evidence role |
|---|---|---|
| Civil Registration Authority | Civil registration | Birth registration, child age, child life status |
| National Identity Agency | Population register | UIN, identity status, BRN linkage |
| Social Registry Office | Social registry | Household membership and poverty band predicate |
| MoSD programme MIS | Integrated beneficiary registry | Duplicate enrollment predicate |

Purpose IRI:
`https://id.registrystack.org/solmara/purpose/child-benefit-review`.

Evidence endpoint: `https://evidence.solmara.registrystack.org/v1/evidence`.

Requester-scoped discovery endpoint:
`https://evidence.solmara.registrystack.org/v1/evidence-definitions`.

The application requests four reviewed requirements:

- `https://id.registrystack.org/solmara/requirement/cra-child-benefit/v1`
- `https://id.registrystack.org/solmara/requirement/nia-child-benefit/v1`
- `https://id.registrystack.org/solmara/requirement/sro-child-benefit/v1`
- `https://id.registrystack.org/solmara/requirement/mosd-child-benefit/v1`

Each successful response is a flattened JWS with media type
`application/jose+json`.

## Positive Path

Persona: Mateo Santos, `2300010248`.

Expected claims:

| Claim | Expected result |
|---|---|
| `birth-is-registered` | Pass: Mateo has a registered BRN. |
| `population-record-active` | Pass: Mateo's population record is active. |
| `child-age-under-5` | Pass: Mateo is under 5 at the lab clock. |
| `household-below-poverty-threshold` | Pass: household score band is eligible; raw score is not disclosed. |
| `not-already-enrolled` | Pass: no active child support enrollment exists. |

Registry Evidence calls the CRA, NIA, SRO, and Programme Records APIs through
separate reviewed source definitions. Each request selects one requirement and
returns only its approved concepts. The child-benefit application verifies and
combines those assertions, but does not receive source rows or a composed
eligibility decision from Evidence.

## Failure Cases

| Persona | Case | Expected result |
|---|---|---|
| Esteban Cruz | Deceased control persona | Fails life-status check before enrollment eligibility. |
| Hana Aquino | Household above threshold | Fails `household-below-poverty-threshold`; raw poverty score remains undisclosed. |
| Karim Kone | Unregistered birth | Fails `birth-is-registered` and routes to "register the birth first" rather than a dead end. |
| Tomas Bello | Duplicate enrollment | Fails `not-already-enrolled` because an active enrollment already exists. |

## Purpose Denial

The smoke must submit a complete child-benefit Evidence request with an
unsupported purpose. Evidence must return HTTP 403 with the generic
`not_authorized` problem before source access. The response must not reveal
whether a requirement, purpose, subject, grant, or source would otherwise
match. Raw household fields are not part of any child-benefit requirement.

## Smoke Expectations

The story smoke asserts:

1. Metadata discovery returns the child benefit offering and the purpose IRI
   from `docs/purposes.md`.
2. Mateo's four Evidence requests return all five approved positive concepts.
3. Each response is a signed assertion and none contains an
   `eligible-for-child-benefit` application decision.
4. Each listed failure case returns a failed predicate with no raw protected
   source row in the response.
5. An unsupported-purpose request returns HTTP 403 `not_authorized` without
   reflecting a protected field.
6. Message text is not asserted.
