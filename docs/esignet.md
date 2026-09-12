# Native eSignet 2 with BREG

The optional identity profile runs eSignet `v2.0.0-beta.1` at commit
`df0d0e771dae16eb2597b8e5b5dc65e70baa7f86`, its matching UI, and the native
an unreleased BREG provider candidate built from the companion provider
checkout. BREG is the population system of record and the retained ThunderID
dev issuer authenticates the provider. Relay integration is deferred.

The provider verifies the OTP before contacting ThunderID or BREG. It checks only
`uin,status`, then asks for fresh consent on every login. Only approved, mapped,
provisioned fields are read from BREG's `data.domainData`. The pairwise OIDC
`sub` is derived with an independent HMAC secret. The Portal separately requests
`person_reference` as an essential, consented opaque reference. That reference
is a governed BREG field distinct from both the challenge UIN and the pairwise
subject. Refusing that claim does not create a Portal session.

The UI build applies reviewed locale and dependency patches to that exact
source. It retains Thunder React 0.11.2 and pins the resulting npm lockfile
checksum in the image metadata. See [UI build maintenance](../docker/esignet-ui/README.md)
for dependency refresh and validation commands.

## Build and start locally

Prerequisites: Docker with Buildx, Go 1.26, Node with pnpm, uv, just, and matching
native `bregctl` and `breg` tools supporting `--issuer-port`, `dev
export-client`, and `dev token`. The fixture uses the native toolchain's own
PostgreSQL and ThunderID lifecycle. Put the matching candidate binaries on
`PATH` if the installed release lacks these commands. See [the BREG
fixture](../breg/README.md) for its bounded seed population and exact candidate
requirements.

From the `esignet-relay-authenticator` checkout:

```sh
GOTOOLCHAIN=go1.26.8 go test -race ./...
./integration/test.sh
./integration/build.sh
# Load an image for this machine, without publishing.
./integration/build.sh --load
```

The multiarchitecture archive is `dist/esignet-breg-candidate.oci.tar`.
The `--load` command loads the matching local architecture into Docker. Set
`SOLMARA_ESIGNET_CANDIDATE_IMAGE` in the Lab's ignored `.env` to the exact image
tag loaded by that build. The Lab does not supply a default candidate tag or
claim released support. No registry publication is needed for this journey.

From this Lab checkout:

```sh
just setup
uv run scripts/gen-secrets.py
uv run python breg/generate-seeds.py --check
just esignet-fixture-start
uv run python breg/dev.py verify
uv run scripts/smoke-esignet.py
node scripts/smoke-esignet-login.mjs
just esignet-protocol-proof
```

Open `http://127.0.0.1:4300`, select **Sign in with SolmaraID**, enter one of the
synthetic fixture identities (for example `2300018263`), and use the synthetic
OTP `111111` (the generated value is stored in ignored
`config/evidence/local/esignet-v2/static-otp`; `ESIGNET_DEMO_OTP` overrides the
browser test input if you changed it). Accept the
required opaque person-reference claim and the optional given/family names you
want to share.
The default Portal journey requests only these fields. The UI defaults to English
and preserves an explicitly supplied language preference.
The Portal validates the signed ID token and signed UserInfo before opening the
service catalogue. This isolated profile uses the Portal's mock programme
backend while its identity journey uses real eSignet, ThunderID, BREG and PostgreSQL.

`just esignet-fixture-stop` stops only this profile and preserves its state.
Do not use a volume reset to upgrade it. The new database, Redis, provider-config
and host-key volumes use `esignet-v2-*` names; existing Java-era volumes stay
untouched.

## Trust and deployment

The provider's strict YAML is selected by `REGISTRY_ESIGNET_CONFIG_FILE`.
`breg/dev.py start` exports only the dedicated source client's credential and
writes ignored local configuration. Private files are mounted into a dedicated
configuration volume readable by the nonroot eSignet process. Portal client
assertion keys, provider-to-ThunderID keys, PSUT secrets, and eSignet signing keys
remain independent. Static OTP and the software host keystore are explicitly
synthetic-demo choices. The client registers only `mosip:idp:acr:static-code`;
it does not claim generated-code assurance. Production OTP delivery is outside
this candidate.

The root discovery URL is `/.well-known/openid-configuration`; authorization,
token, keys and UserInfo endpoints are under `/oauth2`. The matching UI serves
`/signin`. Administrative client-management and bootstrap routes are accessible
only inside the container network. Public proxies exclude those routes and
avoid logging OAuth query strings.

`compose.esignet.yaml` integrates the candidate with the full local Lab.
`compose.coolify.esignet.yaml` describes the matching hosted overlay, with
required immutable image references. Hosted configuration validation does not
publish artifacts or apply a cutover. Its operator must provision the BREG
endpoint and dedicated issuer client, use reachable service addresses, and supply
the provider's mounted files before any separately authorized deployment.

## Troubleshooting and verification

- If startup reports `configuration invalid` or `configuration YAML invalid`,
  check the YAML field names,
  mounted paths, source field inventory, and explicit demo verifier setting.
  A missing production verifier fails startup.
- If client registration fails, verify that service and UI use the same pinned
  source plus the BREG patch, and rerun the one-time private seeder. The pinned
  client API requires UTC timestamps with milliseconds. It is not the old SQL
  client schema. If existing registration evidence is missing or its key or relying
  party differs, configure a fresh client ID **and a fresh signing key**, then
  update both matching Portal values before seeding. The native host requires
  each client's public key to be unique; changing only the ID is insufficient.
  Preserve the private `esignet-v2-seed-state` volume with the database so routine
  restarts can verify the existing registration.
- After upgrading the authored authentication flow, invalidate only its definition
  cache and recreate the eSignet host. Redis retains the definition for up to a
  day, and the host also caches its graph in memory; replacing the image alone
  can continue to run the old flow. In this isolated profile the exact Redis key
  is `esignet::runtime:esignet:flow:definition:flow-breg-otp`. Delete only that key
  with the fixture's `redis-cli DEL`, then run Compose `up -d --no-deps
  --force-recreate esignet`. Keep every other Redis key and database volume;
  do not use `FLUSHDB`, `FLUSHALL`, or a volume reset. Pause active proof flows
  before this upgrade and start a fresh login afterwards.
- For dependency errors, verify native BREG and ThunderID are running and that
  Docker can reach host loopback via `host.docker.internal`. The client assertion
  audience remains the exported issuer origin even when transport uses another
  address. Resource and scopes remain the exact exported client values.
- Keep the same PSUT secret to preserve pairwise subjects across restart. Check
  clocks and restart the login if its five-minute attribute context expires.
- For callback failure, verify exact issuer and redirect URI, Portal key/JWK
  registration, and consent to the required business claim. Do not bypass JWT
  validation or substitute an unverified identifier.
- Set adapter-node's `ORIGIN` to the canonical public Portal URL. The Compose
  configurations derive it and the registered callback from the same
  `SOLMARA_PORTAL_PUBLIC_BASE_URL`, with the configured local port as fallback.
  Local HTTP must be explicit: without `ORIGIN`, adapter-node can infer HTTPS
  and correctly fail the strict callback URI check for an HTTP fixture. Keep
  the canonical origin configuration instead of trusting forwarded headers.

Run `just lint`, `just test`, `just compose`, and the two eSignet smoke commands
for changed Lab boundaries. The provider's race and adapter suites cover nil
pre-consent probes, empty consent, state restoration, bounded token caching,
source refusal, cancellation and redaction. `just esignet-protocol-proof` exercises fresh
consent and the host's signed/encrypted UserInfo implementations with separate
synthetic clients. Full programme acceptance requires the full Lab services.
