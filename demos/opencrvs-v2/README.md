# OpenCRVS v2 interoperability demo

This optional, isolated demo is designed to prove a narrow interoperability
path from a live OpenCRVS deployment through Registry Relay and Registry
Notary. It does not add an authority to the normal Solmara topology and it is
not started by `just up`.

The offline fixtures and compiler checks work today with the exact development
Registryctl override below, and Compose validation works without live inputs.
The live proof does not complete on the released Registry Stack v0.15.2
runtime, even with that compiler. The paired pre-release candidate path below
has completed the full live proof. Deployment still requires a later Registry
Stack release containing the same fixes.

The intended live path is:

1. Relay sends form-encoded client credentials to
   `POST https://auth.<opencrvs-host>/token` with
   `grant_type=client_credentials`, `client_id`, and `client_secret`.
2. A bounded Rhai adapter makes one exact
   `POST https://gateway.<opencrvs-host>/events/events/search` request.
   It reads the flattened OpenCRVS v2 declaration keys such as `child.nid`,
   `mother.name`, and `informant.relation`.
3. Relay emits six booleans and no identifying source values.
4. Notary evaluates five predicate claims.
5. Notary issues a holder-bound `dc+sd-jwt` through `POST /v1/credentials`.
6. The runner verifies the issuer signature, the exact five disclosed
   predicate names and `true` values, and the ephemeral `did:jwk` holder
   binding in memory.

## Release boundary

OpenCRVS returns exactly `access_token` and `token_type` from its token endpoint,
without the otherwise common `expires_in` member. The two Registry Stack
surfaces are at different release stages:

- The released v0.15.2 Relay has the strict no-expiry OAuth decoder, but its
  durable completion-seed path treats the absent token lifetime as a different
  credential mode. It rejects this script plan before OpenCRVS dispatch, so
  v0.15.2 cannot complete the live proof.
- The released Registryctl v0.15.2 cannot author that contract.
- Registry Stack commit
  [`d6f3ed71680e45af4eeac37b0ee1c7bab69bb23e`](https://github.com/registrystack/registry-stack/commit/d6f3ed71680e45af4eeac37b0ee1c7bab69bb23e)
  adds the pending Registryctl authoring support only. It is not a release and
  does not include the Relay state-plane fix.

The pending Registryctl change adds this explicit project setting:

```yaml
response_profile: oauth2_bearer_no_expiry
```

That profile accepts only HTTP 200 with a JSON object containing exactly
`access_token` and case-correct `token_type: Bearer`. It rejects `expires_in`
and every other extra response member. Token caching is disabled: Relay
acquires a token for the current bounded consultation and does not retain it
for another consultation. Registryctl does not infer freshness from unsigned
JWT claims, and the existing expiry-based profile is unchanged.

Until the next Registry Stack release is pinned in `versions.env`, offline
authoring development must use a Registryctl binary built from that exact
commit in a dedicated clean Registry Stack worktree:

```sh
registry_stack_checkout=/absolute/path/to/registry-stack-oauth-no-expiry
git clone https://github.com/registrystack/registry-stack.git \
  "$registry_stack_checkout"
git -C "$registry_stack_checkout" switch --detach \
  d6f3ed71680e45af4eeac37b0ee1c7bab69bb23e
cargo build --locked --manifest-path "$registry_stack_checkout/Cargo.toml" \
  -p registryctl --bin registryctl

export OPENCRVS_DEMO_REGISTRYCTL="$registry_stack_checkout/target/debug/registryctl"
export OPENCRVS_DEMO_REGISTRYCTL_SOURCE_COMMIT=d6f3ed71680e45af4eeac37b0ee1c7bab69bb23e
```

The runner rejects an override outside its Registry Stack worktree, a dirty
tracked source tree, or a checkout at any other commit. Sanitized evidence
records both the declared source commit and the compiler executable SHA-256.
Do not change `versions.env` to represent this development build as a release.
This compiler-only override enables fixture and authoring work. Commit
`d6f3ed71680e45af4eeac37b0ee1c7bab69bb23e` does not make the v0.15.2 Relay
capable of completing the live consultation.

### Optional pre-release live proof

A pre-release live proof requires a later exact Registry Stack candidate commit
that contains the Registryctl change above, the Relay no-cache state-plane
handling, and active script-budget accounting that excludes bounded
Relay-owned source waits. Build Registryctl and the Relay image from the same
clean source checkout. Do not pair the compiler-only commit above with a Relay
image from another commit.

From the Solmara repository root, after setting `candidate_commit` to that
reviewed 40-character commit:

```sh
registry_stack_checkout=/absolute/path/to/registry-stack-candidate
candidate_commit=REPLACE_WITH_REVIEWED_40_CHARACTER_COMMIT
git -C "$registry_stack_checkout" fetch origin
git -C "$registry_stack_checkout" switch --detach "$candidate_commit"
just opencrvs-demo-candidate-build "$registry_stack_checkout"
```

The candidate builder verifies the clean checkout, builds Registryctl and a
labeled Relay image for the Docker server's native `amd64` or `arm64`
architecture from its exact `HEAD`, then prints the binary path, image tag,
commit, platform, and five required `export` commands. Copy those final five
export lines into the shell that will run the demo. Do not evaluate the entire
build output as shell code. The host-native Relay image is deliberate. It lets
the one-shot Rhai worker retain its 128 MiB sandbox on Apple Silicon instead of
placing that sandbox around Rosetta. The published Notary image remains on the
release platform configured by `REGISTRY_STACK_PLATFORM`.

Before starting live services, the runner requires the compiler checkout to be
clean at that commit and requires both declared source commits to match. It
also inspects the Relay image for the matching
`org.opencontainers.image.revision` label and the exact
`attribute-release,crosswalk-runtime` feature label. Sanitized evidence records
the compiler executable SHA-256 and the inspected Relay image ID. The proof
re-inspects the running Relay and Notary containers. It fails if the Relay
image ID, image reference, source revision, or feature label differs from the
declared identity, or if the Notary image reference differs from the pinned
digest. These paired overrides are for local development proof only. Do not
deploy the candidate or replace release pins with its tag.

Once a release contains the Registryctl profile, Relay's explicit no-cache
state-plane handling, and the active script-budget correction, update the
coordinated Registryctl, source, Relay, and Notary pins through the normal
release-adoption process. Then unset all five development override variables
and run:

```sh
just release-pins vX.Y.Z
just opencrvs-demo-test
just review-release vX.Y.Z
```

Run the live proof with those released pins before deployment. There is
currently no hosted Compose file or deployment recipe for this demo, so the
local proof must not be presented as hosted deployment evidence.

## Operator input

The runner reads the operator-owned file
`registry-internal/.env.opencrvs` without modifying it. Override its location
with `OPENCRVS_DEMO_ENV_FILE` when the repositories are not sibling checkouts.
The file must define:

- `OPENCRVS_CLIENT_ID`
- `OPENCRVS_SECRET`
- `OPENCRVS_URL`

Provide these selectors either in the process environment or in that external
file:

- `OPENCRVS_DEMO_REGISTRATION_NUMBER`
- `OPENCRVS_DEMO_CHILD_NATIONAL_ID`
- `OPENCRVS_DEMO_TRACKING_ID`

Explicit selector variables take precedence over the runner's legacy fallback.
Their values are never copied into committed files or sanitized evidence.

`OPENCRVS_URL` must be a lowercase, path-free HTTPS DNS host. The runner writes
only its derived `auth.` and `gateway.` origins into
`demos/opencrvs-v2/.runtime/`, which is ignored and removed by the down command.
Client credentials remain environment references throughout. Do not copy the
operator file, its values, live origins, or generated runtime closure into
tracked files or a support report.

## Commands

The checks available without a live runtime are:

```sh
just opencrvs-demo-test
just opencrvs-demo-compose
```

With all five matching development overrides above set, or after a compatible
Registry Stack release is pinned and those overrides are unset, run the live
path from the repository root with cleanup guaranteed:

```sh
(
  trap 'just opencrvs-demo-down' EXIT
  just opencrvs-demo-up
  just opencrvs-demo-proof
)
```

`opencrvs-demo-test` runs the runner unit tests plus Registryctl fixture,
compiler, and build checks without reading live OpenCRVS inputs.
`opencrvs-demo-compose` validates Compose without starting services or reading
operator secrets. On the released v0.15.2 runtime alone, do not treat a
successful offline or Compose check as a live interoperability result.
`opencrvs-demo-up` requires either the five matching candidate overrides or
compatible release pins, plus Docker, OpenSSL, the external operator inputs,
and network access to the derived OpenCRVS hosts. It creates disposable local
keys, TLS material, PostgreSQL state, and the ignored compiled closure, then
starts only the demo services. `opencrvs-demo-proof` requires that topology to
be running. It performs three pre-dispatch negative controls, one exact
known-record search, one exact syntactically valid no-match search, and direct
credential issuance.

Each negative control must return its expected HTTP status and stable problem
code with zero dispatches. The no-match control requires `birth-record-exists`
to be `false` and all four dependent predicates to be `null`.

The subshell trap runs `opencrvs-demo-down` after success or failure. That
command removes the demo containers, volumes, and ignored runtime closure
without reading operator or generated runtime credentials, and is safe to
rerun after credentials are missing, incomplete, or rotated.

## Evidence and privacy

Successful proof writes only
`output/opencrvs-v2-demo/evidence.json`. The output directory is ignored.
Evidence includes artifact hashes, image digests, bounded dispatch counts,
predicate results, credential metadata, cryptographic verification booleans,
and the authoring compiler identity. It reports public authored bounds
separately from effective private runtime limits, and requires exactly one
credential dispatch plus one source dispatch for each live consultation. A
development proof records the exact shared source commit, compiler executable
SHA-256, running Relay image ID, and running Notary image ID. Issued credentials
must be currently valid within 30 seconds of clock skew and match the authored
10-minute lifetime.

The runner fails before writing evidence if its scan finds any of the following
in compiled configuration, existing evidence, container logs, or the pending
evidence object:

- OpenCRVS client ID or secret
- OAuth access token
- raw credential
- registration, national ID, or tracking selectors
- the known child name when present in the operator file
- another bearer-shaped token

The raw OpenCRVS response, holder private key, OAuth token, and issued credential
remain memory-only. The evidence reports issuer, audience, scope, and lifetime
from unsigned token claims and labels that parsing explicitly. It does not
claim those metadata fields were cryptographically verified.

Credential issuance uses the canonical Solmara Civil Registration Authority
identifier, `did:web:id.registrystack.org:solmara:authority:cra`, with a
disposable local demo signing key. The runner verifies that local signature and
the credential identity, but this demo does not perform public DID resolution
or prove possession of a production CRA signing key.

## Capability boundary

Implemented and verified offline:

- exact native request construction in the bounded Rhai adapter
- synthetic match, no-match, ambiguity, and malformed-response fixtures
- the compiled strict, non-caching OAuth response contract
- minimized scalar predicate outputs
- the compiler boundary rejecting structured parent outputs
- runner unit verification of `dc+sd-jwt` signature, disclosures, and holder key
- top-level scalar parent-related predicates

Verified live with a same-commit compiler and Relay development candidate.
Reproduction requires that paired candidate or the compatible release:

- OAuth-authenticated native OpenCRVS Events API search through Relay
- Notary evaluation from Relay provenance
- holder-bound `dc+sd-jwt` issuance through `/v1/credentials`
- live pre-dispatch negative controls and sanitized evidence generation

Not demonstrated by this demo:

- structured `parents[]` or representative objects in a credential
- proof that the credential holder is the child’s parent or informant
- registrar-initiated OID4VCI pre-authorized offers
- delivery into a parent’s wallet
- OpenCRVS-triggered issuance
- official OpenCRVS compatibility certification

Issuance is a direct authenticated machine API call to a demo-controlled
ephemeral holder key. Holder binding proves possession of that key only. It is
not an OID4VCI registrar offer, does not deliver a credential to a wallet, and
does not establish that the machine caller or key holder is the child's parent
or informant. The two parent-related scalar predicates report fields in the
source record; they are not relationship proof.

## Troubleshooting

- A Registryctl error naming `oauth2_bearer_no_expiry` means the v0.15.2
  compiler is still selected. Build the exact pending commit above and set both
  development override variables for offline authoring work, or use the future
  release that contains the profile.
- An error about the development Registryctl worktree means the executable is
  outside the declared checkout, the checkout has tracked changes, or its
  `HEAD` differs from `OPENCRVS_DEMO_REGISTRYCTL_SOURCE_COMMIT`. Rebuild from a
  dedicated clean checkout. Do not bypass the provenance check.
- An error requiring a development Relay image means the compiler override was
  selected without all five paired development variables. If the image is
  rejected, confirm its source revision and exact feature labels match the
  compiler candidate. Do not pair artifacts from different commits.
- If the candidate builder cannot find Crosswalk, place the `crosswalk`
  checkout beside the primary Registry Stack checkout as required by Registry
  Stack's source build, then rerun the builder.
- If a candidate image was copied from another machine, rebuild it locally.
  The runner rejects a declared Relay platform that differs from the image
  architecture. This also avoids Rosetta failing inside the worker's fixed
  128 MiB data limit on Apple Silicon.
- A strict no-expiry OAuth probe failure means the token endpoint did not
  return HTTP 200 with exactly the accepted two-member response and
  case-correct `Bearer` value. Verify `OPENCRVS_URL`, credentials, and the
  native `auth.` endpoint. Do not loosen the profile or infer expiry from the
  token.
- A Notary readiness timeout usually means one of the disposable PostgreSQL
  bootstrap, workload identity, Relay, or CEL worker services is unhealthy.
  Inspect `docker compose` status without printing its environment.
- On v0.15.2, a valid evaluation that is rejected with zero OpenCRVS dispatches
  is the known Relay completion-seed blocker. The development compiler override
  alone cannot fix it. Use the exact paired development candidate for local
  proof, or pin the compatible release.
- A rate-limited second live control means the environment no longer has the
  documented effective burst of two. The proof deliberately performs one
  known-record consultation and one no-match consultation back to back.
- An evidence-unavailable response with zero data dispatches means the request
  was denied before OpenCRVS access. On a later compatible runtime, check
  purpose, caller, selector shape, and OAuth response compatibility in that
  order.
- If the sanitized-output scan refuses to write evidence, treat that as a
  privacy failure. Run the down command, inspect locally without sharing raw
  logs, and do not weaken the scan.
- On Apple Silicon, the published amd64 CEL worker needs the bounded 1 GiB local
  ceiling already configured for this demo.
