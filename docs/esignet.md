# Optional eSignet profile

eSignet is an optional authentication profile, not an Evidence authority. The
v0.2.0 authenticator validates the challenge and consent first, then obtains a
short-lived Mint token using the `nia-esignet` private-key JWT client and calls
`POST /v2/resources/population-person/lookups/esignet-userinfo`.

The upstream provider has since moved on. `esignet-relay-authenticator` v0.3.0
replaces the JAR with a Go provider compiled into eSignet `v2.0.0-beta.1`, and
that provider reads a Base Registry Engine registry through one governed lookup
carrying a Registry Mint token. Its Relay support is deferred. This lab deploys
no Base Registry Engine, so it stays on the v0.2.0 JAR profile described here.

The request contains only the selected UIN and consented `fields`. The adapter
parses only `data.domainData`, preserves PSUT, KYC-token and JWS behaviour, and
collapses unresolved, concealed, denied, authentication, and dependency
failures to generic subject-facing results. It never logs selectors, tokens, or
source values.

The deployment verifies the v0.2.0 JAR against its published SHA-256 before
building the eSignet image. The NIA Relay, Mint client, and authenticator private
JWK remain independent operator-owned runtime material.

For hosted deployment, `compose.coolify.esignet.yaml` is applied as an overlay
on `compose.coolify.yaml`. It switches the existing Portal to the exact hosted
issuer, authorization, token, UserInfo, private-key-JWT client, and callback
configuration. The Portal client private key is provided only to Portal and the
one-time eSignet client seeder. It is separate from both the `nia-esignet` Mint
client key held by the authenticator and the `solmara-demo` Evidence client key
used by the programme application.
