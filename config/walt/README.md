# walt.id wallet config (hosted holder wallet)

These files configure the self-hosted walt.id **holder** wallet demonstrator
deployed by `compose.coolify.walt.yaml`. The clean six-authority topology does
not currently expose an OID4VCI issuer. Only the wallet-api holder side is
deployed; walt's issuer-api, verifier-api, and portal are not used.

## Provenance

The `*.conf` files are vendored from
`walt-id/waltid-identity` at `docker-compose/wallet-api/config/` (release
`0.20.2`). They are copied verbatim except for the three deltas below. The
config-loader service in the compose file clones this directory into a named
volume and mounts it at `/waltid-wallet-api/config` (Coolify does not seed
compose bind mounts from the repo; see the runbook). `Caddyfile` and this
`README.md` are excluded from that mount.

## Deltas from stock walt

1. **`registration-defaults.conf`** — `defaultKeyConfig.keyType` is `Ed25519`
   (stock: `secp256r1`). This keeps holder keys compatible with the Registry
   Notary `EdDSA` plus `did:jwk` binding used when an authority project exposes
   a reviewed issuance flow.
2. **`auth.conf`** — the login-session `encryptionKey` / `signKey` / `tokenKey`
   are read from the environment (`WALT_AUTH_*`) instead of walt's public sample
   values, and fail-closed if unset.
3. **`dev-mode.conf`** — `enableDidWebResolverHttps=true` (stock: `false`) so the
   wallet resolves authority `did:web` issuers over HTTPS.

## Ingress

`Caddyfile` keeps only walt's demo-wallet site block: it serves the web wallet
on `:7101` and proxies `/wallet-api/*` to `wallet-api:7001` on the same origin.
Coolify routes `wallet.solmara.registrystack.org` to this Caddy.
