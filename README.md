# Solmara Lab

Solmara Lab is a fictional Registry Stack adopter lab for authority-owned,
independently signed evidence. The programme application composes assertions.
Registry Evidence does not make a cross-authority programme decision.

The reset has two evidence cadences:

- CRA birth, NIA population, and SRO poverty requirements read checkpointed,
  immutable SQLite extracts.
- CRA civil links and death status, MoSD enrolment, SIPF pension and survivor
  cases, and NAgDI agriculture requirements use named Relay V2 exact lookups.

Six Evidence cells have distinct providers, issuers, signing keys, JWKS, audit
sinks, subject-binding secrets, and endpoints. Five Relays expose only the
named non-enumerating operations needed by the lab. NIA's Relay is reserved for
the optional eSignet UserInfo profile; NIA Evidence reads its own extract.

## Release prerequisite

Registry Stack v0.19.0 cannot run this topology. Its Mint cannot issue the
Relay-compatible scope and purpose claims required by Relay V2, and its
Evidence runtime cannot classify Relay's concealed `consultation.unresolved`
response as a data-free unresolved consultation. Registry Stack v0.21.0 is the
first coherent release that contains both capabilities and publishes official
Relay, Evidence, and Mint runtime images. Solmara tracks that release line and
currently pins v0.22.0, recording its release tag and source commit, those
official OCI references by digest, and the `relayctl` binary checksum in
`versions.env`. The release handoff and every hosted deployment consume those
same full references without reconstructing them from a second deployment
input.

The eSignet profile uses the separately released
`esignet-relay-authenticator` v0.2.0 JAR and its matching SHA-256 checksum. No
source-build, locally wrapped runtime, floating-tag, or v0.19 compatibility
fallback is accepted.

## Quick start

Prerequisites are Docker with Compose, `just`, `uv`, and `pnpm`.

```bash
just setup
just generate
just relay-check
just compose
just up
just evidence-check
just smoke
just programme-acceptance
just lifecycle-proof
```

`just generate` publishes five mutable Relay databases and three versioned
immutable extracts below ignored `output/sqlite/`. It also creates ignored
runtime secrets and public projections. An active extract is never overwritten
in place.

Local entry points after startup are:

- Visitor Center: `http://127.0.0.1:4301`
- Programme portal: `http://127.0.0.1:4300`
- Authority Evidence gateway: `https://localhost:4341/evidence/{authority}`
- Static metadata: `http://127.0.0.1:4331`

The gateway strips `/evidence/{authority}` before forwarding. Application code
uses six authority base URLs and never assumes a national Evidence host.

## Architecture

| Authority | Evidence source | Relay V2 role |
|---|---|---|
| CRA | immutable birth extract; Relay for death and civil link | `civil-person/death-by-uin`, `civil-person/citizen-link-by-uin` |
| NIA | immutable population extract | `population-person/esignet-userinfo` for eSignet |
| SRO | immutable poverty extract | none |
| MoSD | Relay lookup | `beneficiary-enrolment/by-uin` |
| SIPF | Relay lookups | `pension-payment/by-pensioner-uin`, `survivor-case/by-spouse-uin` |
| NAgDI | Relay lookups | `farmer/voucher-by-farmer-id`, `livestock-herd/movement-by-farmer-id` |

One lab Mint issues tokens for the common `solmara-runtime` audience. Every
operation still has a distinct client, fixed scope, canonical purpose claim,
access profile, and disclosure profile. This shared audience is a lab
convenience, not production tenancy guidance.

Direct extracts have a maximum age of 86,400 seconds and assertions valid for
at most 3,600 seconds. Relay-backed assertions are valid for at most 300
seconds. Every response is a flattened ES256 JWS and is verified against the
JWKS of the authority endpoint that issued it.

## Publisher lifecycle

From `generator/`:

```bash
uv run python -m solmara_lab.publisher --root .. publish-all
uv run python -m solmara_lab.publisher --root .. mutate-mosd \
  --uin 2300010248 --duplicate-flag true \
  --recorded-at 2026-08-12T12:00:00Z
uv run python -m solmara_lab.publisher --root .. publish-extract \
  --authority sro --published-at 2026-08-12T12:00:00Z \
  --extract-id sro-poverty-20260812T120000Z
```

The live MoSD mutation is visible on the next Relay-backed Evidence request
without a restart. A newly named SRO extract is not visible until only the SRO
Evidence cell is rebound and restarted. Invalid, stale, or overwritten extracts
fail closed. Run lifecycle smoke in isolated volumes or restore the deterministic
fixture state afterward.

## Verification

```bash
just relay-check          # relayctl check --production, generate, test, package
just evidence-check       # six bundles, 11 requirements, source/error fixtures
just lint                 # metadata, redaction, portal and Visitor Center checks
just test                 # Python and web unit/integration suites
just compose              # local, hosted, Coolify, and optional eSignet config
just smoke                # local UI and Relay health
just programme-acceptance # programme stories and generic denial controls
just lifecycle-proof      # live Relay and immutable-extract cadence
just portal-live-e2e
just home-live-e2e
just smoke-esignet        # optional NIA Relay V2 login profile
```

Generated SQLite databases, Relay packages, runtime bundles, keys, secrets,
tokens, and private audit records are not tracked. Public metadata and governed
Relay/Evidence authoring inputs are tracked.

## Repository map

- `relays/` contains five authority-governed Relay V2 projects.
- `evidence/cells/` contains six authority Evidence bundle templates and
  runtime bindings.
- `generator/solmara_lab/publisher.py` publishes deterministic SQLite sources.
- `scenarios/` and `scenario-runner/` route requirements to authority cells,
  verify multiple JWKS, and compose application outcomes.
- `portal/` and `home/` display safe authority, issuer, and source-type labels.
- `metadata/` and `requests/registry-lab/` publish discovery and request
  examples for the reset.

## Hosted rollout and recovery

Deploy the new V2 services and new volumes alongside the existing deployment.
Smoke the new endpoints before switching application and metadata routing.
After the switch, disable superseded services but retain their volumes. Deleting
old data is a separate, explicitly approved cleanup and is not part of this
reset.

All Solmara data is synthetic. Never put real people, credentials, hosted
deployment evidence, private audit output, or private keys in this repository.
