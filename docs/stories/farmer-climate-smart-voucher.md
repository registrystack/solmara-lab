# Farmer voucher and livestock movement

NAgDI owns one live read-only SQLite publication and two isolated Relay V2
lookups.

`farmer/voucher-by-farmer-id` supports requirement `nagdi-voucher/v1` under
`voucher-eligibility-review`. It yields the three signed concepts
`farmer-registered`, `data-use-authorized-for-purpose`, and
`eligible-for-climate-smart-input-voucher` after reviewing the minimum governed
voucher facts.

`livestock-herd/movement-by-farmer-id` supports requirement
`nagdi-livestock/v1` under `livestock-movement-control`. It yields
`registered-herd`, `origin-district-not-quarantined-for-species`, and
`eligible-for-livestock-movement-permit`.

Each operation has a distinct Mint client, scope, purpose claim, access profile,
and disclosure profile. Voucher authority cannot call the livestock operation
and livestock authority cannot call the voucher operation. Neither route
offers enumeration.

Positive, unauthorized-data-use, redeemed-voucher, quarantine, wrong-purpose,
unresolved, malformed-row, unavailable-source, and unavailable-audit cases are
tested. UI and logs never render the farmer selector or source row.
