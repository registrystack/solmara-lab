# Synthetic population registry for eSignet 2

This local fixture runs an authored Base Registry Engine project over its own
PostgreSQL database. Registry Mint issues OAuth access tokens to separate
operator and eSignet clients. It uses the native `bregctl dev` lifecycle and
installed matching `bregctl`, `breg` and `mint` binaries, without a Registry Stack
source checkout. The tools must support `bregctl dev export-client`.

The fixture contains the first twelve canonical synthetic citizens from
`ministries/interior-population/fixtures/population_person.csv` and one explicit
inactive negative case. It is an isolated authentication test population, not a
replacement for the ministry's thousand-record scenario database. The model is
ordinary registry configuration; no Rust domain types or special runtime routes
are required.

## Start and verify

Install the matching native Registry Stack toolchain on `PATH`, start Docker,
and generate the lab's ignored secrets with `uv run scripts/gen-secrets.py`.
Then, from the repository root:

```sh
uv run python breg/generate-seeds.py --check
bregctl check breg/population
uv run python breg/dev.py start
uv run python breg/dev.py verify
```

### Build a pinned native toolchain

When an installed toolchain lacks `dev export-client`, build all three tools
together. The following uses Registry Stack source commit
`2710bf5163c08f9699e486a05e46603184229155`, whose native lifecycle includes the
required command, and its pinned Rust 1.95.0 toolchain and Cargo lockfile. Use
fresh directories outside the lab checkout:

```sh
git clone https://github.com/registrystack/registry-stack.git registry-stack-breg-tools
cd registry-stack-breg-tools
git checkout --detach 2710bf5163c08f9699e486a05e46603184229155
CARGO_INCREMENTAL=0 CARGO_PROFILE_DEV_DEBUG=0 CARGO_PROFILE_TEST_DEBUG=0 \
  cargo build --locked -p registry-breg --features registry-breg/runtime \
  -p registry-bregctl -p registry-mint --bins
mkdir -p ../breg-tools/bin
install -m 755 target/debug/breg target/debug/bregctl target/debug/mint ../breg-tools/bin/
export PATH="$(cd ../breg-tools/bin && pwd):$PATH"
bregctl dev export-client --help
```

This pins build inputs; it does not promise identical binary bytes across host
toolchains. Return to the lab and run the checks above against a fresh fixture
before relying on that build. This exact source pin was built on macOS arm64
with Rust 1.95.0 and passed all thirteen live fixture checks. A coordinated
native stop/start preserved record identifiers, revisions, field values,
package revision and client credentials while switching to those binaries.
Normal startup uses the installed binaries only. Stop an existing fixture
normally before changing its binary set; never remove its data to change tools.

The wrapper calls `bregctl dev breg/population --breg-port 18190 --mint-port
18191 --database-port 55449`. Native startup rehearses the authored journeys
against real PostgreSQL, activates the compiled package, starts the services,
and creates the explicit seeds through authenticated BREG HTTP requests.

It exports only the `esignet` client's private ES256 JWK into the owner-only,
ignored `config/evidence/local/esignet-v2/` directory. The provider configuration
references `mint-private.jwk`, `psut-secret` and `static-otp` under its container
mount `/etc/registry-esignet`. Mint's token endpoint transport address is
`http://host.docker.internal:18191/token`; its client assertion audience remains
`http://127.0.0.1:18191/token`. The private key's `kid` comes from the JWK.
The lab's generated static OTP is explicitly enabled for this synthetic fixture.

BREG listens on `http://127.0.0.1:18190`; containers use
`http://host.docker.internal:18190`. Docker must support reaching host loopback
services through that address, as OrbStack does. The wrapper's port options
apply only to first start; the native lifecycle preserves retained ports and
refuses conflicting authored inputs. It never resets another service.

The live verification obtains fresh tokens without writing or printing them.
It checks the exact minimum account projection and a narrower consent
projection, concealed missing/inactive identities and unknown selectors,
withheld fields, denied source list/get/create, anonymous and invalid bearer
refusals, and rejection of a duplicate UIN by the separate operator role.

```sh
uv run python breg/dev.py stop
```

Stop preserves this fixture's database, credentials, and seed checkpoints.
Restart reuses them. Do not remove retained state to apply model changes. Follow
the native governed package lifecycle or create a separate disposable project.
Regenerate committed seeds explicitly with `uv run python breg/generate-seeds.py`
before a fresh fixture's first start; changing seeds after startup does not
overwrite retained citizens.

## Governed HTTP contract

The eSignet client has only the `lookup` operation, the `by-uin` selector, and
six readable fields: `uin`, `status`, `givenName`, `familyName`, `birthdate`, and
`gender`. The registry enforces the unique UIN constraint. Its row boundary
compares `status` with Mint's fixed `registry_identity_status: active` claim.
The caller-provided UIN is a selector input, never an authorization grant.
The source has no list, get, create, or patch grant. `operatorNote` remains
operator-only. The operator's unrestricted row finding is intentional for
maintenance and seeding; its credential is never exported to eSignet.

After the challenge has been verified, the provider checks only:

```http
POST /v1/records/population:lookup?accessProfile=esignet-source&%24select=uin%2Cstatus
Authorization: Bearer <short-lived token>
Content-Type: application/json

{"selector":"by-uin","values":{"uin":"2300010248"}}
```

The result is a Registry Record envelope. Actual facts are exclusively in
`data.domainData`, here exactly `{"uin":"2300010248","status":"active"}`.
For consented claims the provider requests the intersection of requested claim
fields with its provisioned fields using `$select`. It never falls back to
enumerating records. `givenName` and `familyName` are HTTP names for authored
logical fields `given-name` and `family-name`.

The portal requests `individual_id` explicitly as an essential consented claim.
It maps to the governed `uin` field for business-record correlation. The OIDC
`sub` remains the pairwise pseudonymous subject token and never substitutes for
that identifier. Display names use the separate `given_name` and `family_name`
claims; this fixture does not invent a stored full-name field.

A missing identity, inactive identity, or unresolved selector produces
`404 lookup.unresolved`; denied profile or operation produces concealed
`404 resource.not_found`. A rejected presented token produces
`401 authentication.refused`. The provider collapses concealed subject failures
and does not expose upstream differences. UIN uniqueness prevents an ambiguous
stored match, and BREG also fails unresolved lookup closed.

Native `tests/journeys.yaml` rehearses create, exact lookup, and missing lookup.
`breg/dev.py verify` exercises the wider HTTP refusal boundary, including routes
that cannot appear as authorized operations in a native journey fixture.
