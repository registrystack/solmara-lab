# Birth to child benefit

Purpose: `child-benefit-review`.

The programme requests four independently signed authority assertions and owns
the final outcome:

| Authority | Requirement | Source | Concepts |
|---|---|---|---|
| CRA | `cra-child-benefit/v1` | immutable birth extract | `birth-is-registered`, `child-age-under-5` |
| NIA | `nia-child-benefit/v1` | immutable population extract | `population-record-active` |
| SRO | `sro-child-benefit/v1` | immutable poverty extract | `household-below-poverty-threshold` |
| MoSD | `mosd-child-benefit/v1` | Relay lookup | `not-already-enrolled` |

Mateo Santos, UIN `2300010248`, is the positive synthetic persona. All five
concepts are true. The application may therefore show the positive child
benefit outcome, while each source row remains with its authority.

Controls cover deceased or aged-out children, an above-threshold household, an
unregistered birth, duplicate enrolment, and wrong purpose. An unregistered
birth is a valid CRA record with no BRN and produces signed false, not an
unresolved consultation. The mutable MoSD source changes on the next request;
the three immutable sources change only after a reviewed replacement is bound
and the owning cell is restarted.

The response surface contains safe authority, issuer, provider, source type,
and verified concept values. It does not contain selectors, tokens, source
rows, raw poverty measures, private audit output, or JWS bodies.
