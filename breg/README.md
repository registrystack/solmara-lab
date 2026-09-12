# Synthetic population registry for eSignet 2

This local fixture runs an authored Base Registry Engine project over its own
PostgreSQL database. The lifecycle's ThunderID issuer issues OAuth access tokens
to separate operator and eSignet clients. It uses installed matching `bregctl`
and `breg` binaries, without a Registry Stack source checkout. The candidate
tools must support `bregctl dev --issuer-port`, `dev export-client`, and
`dev token`. No published Registry Stack release is claimed to support this
candidate fixture yet.

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

When an installed toolchain lacks those commands, build `bregctl` and `breg`
together from the exact reviewed Registry Stack candidate source supplied for
this integration. Use its pinned Rust toolchain and Cargo lockfile, and build in
a fresh directory outside the Lab checkout:

```sh
git clone https://github.com/registrystack/registry-stack.git registry-stack-breg-tools
cd registry-stack-breg-tools
git checkout --detach <reviewed-candidate-commit>
CARGO_INCREMENTAL=0 CARGO_PROFILE_DEV_DEBUG=0 CARGO_PROFILE_TEST_DEBUG=0 \
  cargo build --locked -p registry-breg --features registry-breg/runtime \
  -p registry-bregctl --bins
mkdir -p ../breg-tools/bin
install -m 755 target/debug/breg target/debug/bregctl ../breg-tools/bin/
export PATH="$(cd ../breg-tools/bin && pwd):$PATH"
bregctl dev --help | grep -- --issuer-port
bregctl dev export-client --help
bregctl dev token --help
```

This pins build inputs; it does not promise identical binary bytes across host
toolchains. Return to the lab and run the checks above against a fresh fixture
before relying on that build. The placeholder must be replaced with the exact
reviewed candidate commit and must not be treated as a version or release
promise. Normal startup uses the installed binaries only. Stop an existing fixture
normally before changing its binary set; never remove its data to change tools.

The wrapper calls `bregctl dev breg/population --breg-port 18190 --issuer-port
18191 --database-port 55449`. Native startup rehearses the authored journeys
against real PostgreSQL, activates the compiled package, starts the services,
and creates the explicit seeds through authenticated BREG HTTP requests.

It exports only the `esignet` client's private ES256 JWK into the owner-only,
ignored `config/evidence/local/esignet-v2/` directory. The provider configuration
references `token-client-private.jwk`, `psut-secret` and `static-otp` under its
container mount `/etc/registry-esignet`. ThunderID's token endpoint transport
address is `http://host.docker.internal:18191/oauth2/token`; the private JWT
assertion audience remains the exported loopback issuer origin. The provider's
resource, scopes, and key ID come unchanged from `dev export-client`.
The lab's generated static OTP is explicitly enabled for this synthetic fixture.

BREG listens on `http://127.0.0.1:18190`; containers use
`http://host.docker.internal:18190`. Docker must support reaching host loopback
services through that address, as OrbStack does. The wrapper's port options
apply only to first start; the native lifecycle preserves retained ports and
refuses conflicting authored inputs. It never resets another service.

The live verification obtains fresh tokens through `bregctl dev token` without
printing them.
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
seven readable fields: `uin`, `status`, `personReference`, `givenName`,
`familyName`, `birthdate`, and `gender`. The registry enforces the unique UIN
constraint. Its row boundary compares `status` with the issuer's fixed
`registry_identity_status: active` claim.
The caller-provided UIN is a selector input and never creates authority.
The source has no list, get, create, or patch permission. `operatorNote` remains
operator-only. The operator's unrestricted row finding is intentional for
maintenance and seeding; its credential is never exported to eSignet.

The separate `citizen-self-service-agent` client uses the
`citizen-self-service` profile, `registry:population:self-service` scope, and
`citizen-self-service` purpose. It can only look up `person` through
`by-person-reference` and read `personReference` plus `status`. BREG requires
the selected `person-reference` to equal the verified
`registry_subject_person_reference` claim and requires `status` to equal the
trusted `registry_identity_status` claim fixed to `active` by the agent policy.
All three profiles use the verified token `sub` as their principal. For the
citizen flow, `sub` remains the citizen while the verified client is
`citizen-self-service-agent`; BREG separately requires `act.sub` to match the
operator-configured native actor for that exact client.
The existing eSignet UIN lookup remains a separate profile and client.

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

The portal requests `person_reference` explicitly as an essential consented
claim. It maps to the governed opaque `personReference` field generated with the
fixture. The UIN remains a challenge input and is not the Portal correlation
identifier. The OIDC `sub` remains the pairwise pseudonymous subject token and
never substitutes for that reference. Display names use the separate
`given_name` and `family_name` claims; this fixture does not invent a stored
full-name field.

A missing identity, inactive identity, or unresolved selector produces
`404 lookup.unresolved`; denied profile or operation produces concealed
`404 resource.not_found`. A rejected presented token produces
`401 authentication.refused`. The provider collapses concealed subject failures
and does not expose upstream differences. UIN uniqueness prevents an ambiguous
stored match, and BREG also fails unresolved lookup closed.

Native `tests/journeys.yaml` rehearses create, exact lookup, missing lookup, and
the refusal when a citizen-bound agent changes the selector to another person's
governed reference.
`breg/dev.py verify` exercises the wider HTTP refusal boundary, including routes
that cannot appear as authorized operations in a native journey fixture.
