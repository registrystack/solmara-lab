# Death To Pension Stop And Survivor Benefit

Status: normative for Solmara Lab wave 1 story 2.

## Purpose

This story demonstrates a high-value DPI control: a registered death stops
payments to a deceased pensioner and determines whether a spouse is eligible for
survivor benefit evidence. The SIPF receives minimized predicates, not medical
details or a full civil record.

## Authorities And Registries

| Authority | Registry | Evidence role |
|---|---|---|
| Civil Registration Authority | Civil registration | Death fact, DRN, marriage linkage, current marriage status |
| National Identity Agency | Population register | UIN and life-status propagation |
| Social Insurance and Pensions Fund | Pensions / social insurance | Pension award, payment status, survivor link |
| MoSD programme MIS | Integrated beneficiary registry | Benefit overlap checks where required |

Purpose IRIs:

- `https://id.registrystack.org/solmara/purpose/pension-payment-review`
- `https://id.registrystack.org/solmara/purpose/survivor-benefit-determination`

Evidence offerings:

- `solmara.pension.payment-stop-review`
- `solmara.pension.survivor-benefit-eligibility`

Credential `vct` values:

- `https://id.registrystack.org/solmara/vct/pension-payment-stop-review`
- `https://id.registrystack.org/solmara/vct/survivor-benefit-eligibility`

Credential name: Survivor Benefit Eligibility SD-JWT VC.

## Positive Path

Personas:

- Rafael Nkomo, `2300109568`, deceased pension member.
- Imani Nkomo, `2300118698`, surviving spouse.

Expected claims:

| Claim | Expected result |
|---|---|
| `person-is-deceased` | Pass: Rafael has a registered death event and DRN. |
| `pension-payment-should-stop` | Pass: Rafael has an in-payment award that must be held or terminated. |
| `survivor-is-eligible` | Pass: Imani is linked to Rafael through a current MRN and verified survivor link. |

The pension notary returns payment-stop evidence for SIPF operations and a
survivor benefit eligibility credential preview or issuance for Imani. The
response discloses the death fact and required registration references, but not
cause of death.

## Failure Cases

| Persona | Case | Expected result |
|---|---|---|
| Otto Ferreira | Death not yet registered | `person-is-deceased` fails or returns stale-data reconciliation status; payment is not automatically stopped from unregistered evidence. |
| Lucia Ferreira | Survivor waits for reconciliation | Survivor eligibility cannot pass until Otto's death registration is available. |
| Mina Rahman | Marriage dissolved | `survivor-is-eligible` fails because the MRN has a termination event. |
| Pavel Rahman | Former spouse death control | Confirms the dissolved marriage path uses relationship status rather than name matching. |

## Purpose Denial

The smoke must attempt to request `cause_of_death` or medical death details
under `pension-payment-review`. The response must deny access with problem code
`pdp.purpose_not_permitted`. The SIPF needs the death fact, not the medicine.

The smoke must also cover delegated notary denials:

| Case | Expected problem code |
|---|---|
| Unsupported delegated purpose | `federation.forbidden` |
| Replayed delegated evaluation | `federation.replay` |

## Smoke Expectations

The story smoke asserts:

1. Metadata discovery returns both pension offerings and purpose IRIs from
   `docs/purposes.md`.
2. Rafael's payment-stop evaluation passes.
3. Imani's survivor eligibility evaluation passes and uses the expected
   survivor credential `vct`.
4. Otto and Lucia produce the stale-data or reconciliation path.
5. Mina's survivor claim fails because the marriage is dissolved.
6. Cause-of-death access is denied with `pdp.purpose_not_permitted`.
7. Federation denial smokes assert codes, not message text.
