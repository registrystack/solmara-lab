# Historical Notary PostgreSQL state

Status: historical migration note. This is not an active operations guide.

Solmara Lab previously ran an authority-owned Registry Notary beside each
consultation Relay and retained separate PostgreSQL correctness state for those
services. Registry Notary is absent from Registry Stack v0.18.0 and from the
current Solmara topology.

Preserve any historical database backups and release records for their required
retention period. Do not attach those databases to Registry Evidence, Registry
Mint, or a current Records API Relay, and do not recreate the retired Notary
routes or schemas in another product. Current Evidence is configured from its
reviewed bundle and obtains source data through protected Relay Records APIs.
