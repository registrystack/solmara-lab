# Death to pension stop and survivor benefit

The pension application combines a CRA death assertion and a SIPF active
payment assertion under `pension-payment-review`. The application, not either
Evidence cell, derives whether payment should stop.

CRA calls only `civil-person/death-by-uin` and discloses the governed death
status. SIPF calls only `pension-payment/by-pensioner-uin` and discloses active
payment status. Cause of death, unrelated civil events, payment amount, and
payment history are outside the contracts.

For survivor benefit, the application sends the surviving spouse UIN
`2300118698` to SIPF requirement `sipf-survivor-benefit/v1` under
`survivor-benefit-determination`. SIPF calls only
`survivor-case/by-spouse-uin` and signs `survivor-is-eligible`.

Controls cover death not yet registered, dissolved relationship, unknown cause
of death requirement, wrong purpose, unresolved lookup, dependency failure,
and audit failure. All dependency and authorization failures are generic and
value-free. CRA and SIPF assertions are independently verified against their
own JWKS before composition.
