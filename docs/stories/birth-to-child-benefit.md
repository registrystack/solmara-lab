# Birth To Child Benefit

Status: normative for Solmara Lab wave 1 story 1.

## Purpose

This story demonstrates a canonical CRVS-to-social-protection journey: a
registered birth, a population identity, a household eligibility predicate, and
a programme duplicate check combine to determine child benefit enrollment
eligibility without exposing raw registry rows.

## Authorities And Registries

| Authority | Registry | Evidence role |
|---|---|---|
| Civil Registration Authority | Civil registration | Birth registration, child age, child life status |
| National Identity Agency | Population register | UIN, identity status, BRN linkage |
| Social Registry Office | Social registry | Household membership and poverty band predicate |
| MoSD programme MIS | Integrated beneficiary registry | Duplicate enrollment predicate |

Purpose IRI:
`https://id.registrystack.org/solmara/purpose/child-benefit-review`.

Evidence offering: `solmara.child-benefit.enrollment-eligibility`.

Credential `vct`:
`https://id.registrystack.org/solmara/vct/child-benefit-enrollment-eligibility`.

Credential name: Child Benefit Enrollment Eligibility SD-JWT VC.

## Positive Path

Persona: Mateo Santos, `2300010248`.

Expected claims:

| Claim | Expected result |
|---|---|
| `birth-is-registered` | Pass: Mateo has a registered BRN. |
| `child-age-under-5` | Pass: Mateo is under 5 at the lab clock. |
| `household-below-poverty-threshold` | Pass: household score band is eligible; raw score is not disclosed. |
| `not-already-enrolled` | Pass: no active child support enrollment exists. |

The notary previews or issues the child benefit enrollment eligibility
credential to Mateo's guardian, Elena Dela Cruz. The proof trace shows source
authorities, predicates, and purpose labels, not raw civil or household rows.

## Failure Cases

| Persona | Case | Expected result |
|---|---|---|
| Esteban Cruz | Deceased control persona | Fails life-status check before enrollment eligibility. |
| Hana Aquino | Household above threshold | Fails `household-below-poverty-threshold`; raw poverty score remains undisclosed. |
| Karim Kone | Unregistered birth | Fails `birth-is-registered` and routes to "register the birth first" rather than a dead end. |
| Tomas Bello | Duplicate enrollment | Fails `not-already-enrolled` because an active enrollment already exists. |

## Purpose Denial

The smoke must attempt a request for raw household poverty score or complete
household profile under `child-benefit-review`. The response must deny access
with problem code `pdp.purpose_not_permitted` and must not include the raw
field.

The smoke must also attempt a request with an unrelated purpose, such as
`pension-payment-review`, against the child benefit offering. The response must
deny access with `pdp.purpose_not_permitted`.

## Smoke Expectations

The story smoke asserts:

1. Metadata discovery returns the child benefit offering and the purpose IRI
   from `docs/purposes.md`.
2. Mateo's positive evaluation passes all four claims.
3. The credential preview or issuance uses the expected `vct`.
4. Each listed failure case returns a failed predicate with no raw protected
   source row in the response.
5. Purpose denial returns `pdp.purpose_not_permitted`.
6. Message text is not asserted.
