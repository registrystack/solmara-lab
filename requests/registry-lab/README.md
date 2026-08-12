# Solmara Lab API Workspace

Wave 1 placeholders for the three Solmara stories:

1. Birth to child benefit.
2. Death to pension stop plus survivor benefit.
3. Farmer climate-smart voucher plus livestock movement control.

The active examples call the centralized Registry Evidence
`POST /v1/evidence` endpoint. Each request generates a fresh 32-byte base64url
nonce and names one reviewed requirement. Set `SOLMARA_EVIDENCE_ACCESS_TOKEN`
to a short-lived Mint token before running them. For Local Compose, configure
the client to trust `config/evidence/local/tls/ca.crt`. The hosted environment
names deployment targets and does not claim those targets are currently
available.

No partner-system or governed-ops folders are part of this wave 1 surface.
