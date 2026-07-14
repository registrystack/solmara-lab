# Death To Pension Stop And Survivor Benefit

Status: normative for Solmara Lab wave 1 story 2.

## Purpose

This story demonstrates a high-value DPI control: a registered death triggers a
review of an active pension payment and determines whether a spouse is eligible
for survivor benefit evidence. The pension-review application receives
minimized predicates from the CRA and SIPF Notaries, not medical details or full
registry rows.

## Authorities And Registries

| Authority | Registry | Evidence role |
|---|---|---|
| Civil Registration Authority | Civil registration | Registered death fact |
| Social Insurance and Pensions Fund | Pensions / social insurance | Active pension payment and survivor eligibility |

Purpose IRIs:

- `https://id.registrystack.org/solmara/purpose/pension-payment-review`
- `https://id.registrystack.org/solmara/purpose/survivor-benefit-determination`

Evidence offerings:

- `cra-death-registration-offering`
- `sipf-pensions-pension-case-offering`

Credential `vct` values:

- `https://id.registrystack.org/solmara/vct/survivor-benefit-status`

Credential name: Survivor Benefit Eligibility SD-JWT VC.

## Positive Path

Personas:

- Rafael Nkomo, `2300109568`, deceased pension member.
- Imani Nkomo, `2300118698`, surviving spouse.

Expected claims:

| Claim | Expected result |
|---|---|
| `person-is-deceased` | Pass: Rafael has a registered death event and DRN. |
| `pension-payment-active` | Pass: Rafael has an active in-payment award that requires review. |
| `survivor-is-eligible` | Pass: SIPF has a verified eligible survivor link. |

The pension-review application combines CRA death evidence with SIPF payment
evidence. It does not ask either Notary to make the cross-authority stop-payment
decision. SIPF separately returns survivor eligibility evidence and can issue
the survivor benefit credential for Imani. Neither path discloses cause of
death.

## Failure Cases

| Persona | Case | Expected result |
|---|---|---|
| Otto Ferreira | Death not yet registered | `person-is-deceased` fails or returns stale-data reconciliation status; payment is not automatically stopped from unregistered evidence. |
| Lucia Ferreira | Survivor waits for reconciliation | Survivor eligibility cannot pass until Otto's death registration is available. |
| Mina Rahman | Survivor relationship no longer eligible | `survivor-is-eligible` fails in SIPF evidence. |
| Pavel Rahman | Former spouse death control | Confirms the SIPF relationship status is used rather than name matching. |

## Purpose Denial

The smoke must attempt to request `cause_of_death` or medical death details
under `pension-payment-review`. The response must deny access with problem code
`pdp.purpose_not_permitted`. The SIPF needs the death fact, not the medicine.

## Smoke Expectations

The story smoke asserts:

1. Metadata discovery returns both authority offerings and purpose IRIs from
   `docs/purposes.md`.
2. The application combines Rafael's CRA death predicate and SIPF active-payment
   predicate without treating either source response as a composed decision.
3. SIPF's survivor eligibility evaluation passes and uses the expected
   survivor credential `vct`.
4. Otto and Lucia produce the stale-data or reconciliation path.
5. Mina's survivor claim fails because the marriage is dissolved.
6. Cause-of-death access is denied with `pdp.purpose_not_permitted`.
7. Denial smokes assert stable problem codes, not message text.
