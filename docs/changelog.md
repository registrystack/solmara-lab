# Solmara Lab Changelog

A small dated log of what changed in the visitor center and the lab topology.
Newest entry first.

## 2026-07-30 Optional OpenCRVS v2 interoperability proof

An isolated, opt-in local demo now authors the native OpenCRVS token and
`POST /events/events/search` path through Relay, minimized predicate evaluation
through Notary, and holder-bound `dc+sd-jwt` issuance through the direct machine
API. Offline fixture, compiler, and Compose checks pass. A paired pre-release
compiler and host-native Relay candidate completed the live OpenCRVS search,
Notary evaluation, direct issuance, cryptographic verification, negative
controls, and sanitized evidence scan. The released v0.15.2 path remains
blocked and must not be reported as a released result. Holder binding proves
possession of the demo's ephemeral key, not a parent or informant relationship,
and this is not an OID4VCI wallet flow. Operator credentials and source values
remain outside the repository, and live origins are limited to an ignored
runtime closure.

OpenCRVS omits `expires_in` from its otherwise strict bearer-token response.
The demo therefore selects Registry Stack's explicit
`oauth2_bearer_no_expiry` authoring profile, which disables cross-consultation
token caching, rejects extra response members, and does not infer freshness
from unverified JWT claims. Development uses exact Registry Stack commit
[`d6f3ed71680e45af4eeac37b0ee1c7bab69bb23e`](https://github.com/registrystack/registry-stack/commit/d6f3ed71680e45af4eeac37b0ee1c7bab69bb23e)
in a clean worktree for offline authoring. That commit adds Registryctl support
only. Relay v0.15.2 has the strict decoder, but its durable completion-seed path
rejects the no-cache script plan before OpenCRVS dispatch. The next Registry
Stack release must include both the authoring profile and explicit Relay
state-plane cache-mode handling, plus active script-budget accounting that does
not charge bounded Relay-owned OAuth and source waits. Only then can the live
proof write sanitized evidence using released artifacts. The successful
pre-release local proof records the compiler commit and executable hash plus
the same-commit Relay image ID.
Deployment remains blocked until `versions.env` pins the release and the
coordinated release review passes.

## 2026-07-29 Registry Stack v0.15.2 adoption

The lab now consumes the canonical Registry Stack Relay image directly. The
separate Solmara feature-runtime image, feature selection, publication, and
normal-startup override are removed because governed attribute release is part
of the canonical v0.15.2 Relay build. Explicit `*-dev` recipes still build the
default Relay feature set from the exact pinned source commit without changing
the standalone production path.

The NIA eSignet profile uses the stable attribute-release contract, removing
the retired subject-input and response-cache fields. Hosted Relay bundle
sequence is now a single reviewed value in `versions.env`, enforced by local
bundle verification, offline generation, and the release-candidate workflow.
Every authority also commits version-matched Registryctl schemas and VS Code
and Zed mappings, with CI drift detection, and release review now includes the
value-free capability inventory for both deployment environments. Independently
authored synthetic request witnesses now cover every reachable
Notary-to-Relay consultation binding instead of treating integration-input
fixtures as caller compatibility proof. Every public Relay is now separated
from a loopback-only consultation Relay that shares only the matching Notary
network namespace. Hosted deployment uses separate instance-bound public and
consultation bundle streams and anti-rollback volumes, preventing private
consultation authority and artifacts from appearing on public Relay
endpoints. All six compiler-generated local and hosted runtime closures are
regenerated with the released v0.15.2 Registryctl. All twelve sequence-2 hosted
bundles are signed with a rotated Ed25519 key held in 1Password and verified
against their new public trust anchors. Registryctl reads the private JWK
through an `op://` reference, so bundle generation does not materialize it in
the repository or working tree. Local public and consultation Relay namespaces
use distinct loopback workload issuer processes so neither JWKS listener is
opened onto the shared Compose network.

The hosted cutover also moves Relay state to the `v015` database epoch. The
previous topology persisted PostgreSQL materialization pointers but not their
immutable cache files, so the new persistent Relay cache volumes cannot safely
reuse every `v013` pointer after container replacement. The old databases stay
intact for rollback while the new state plane publishes fresh snapshots.

## 2026-07-25 Registry Stack v0.13.0 adoption

The lab now pins the Registry Stack `v0.13.0` Relay and Notary image digests
and the matching Registryctl binary. All six authored projects pass the
v0.13.0 compiler checks and fixture suites. Regenerated Notary configuration
keeps SD-JWT under credential issuance profiles while removing it from claim
evaluation formats, which now advertise only the canonical claim-result
format.

Relay consultation state uses the release-owned `v013` database epoch. The
idempotent PostgreSQL bootstrap creates new per-authority databases and roles
on fresh or existing clusters, preventing old and v0.13.0 Relay binaries from
sharing the retained result state plane. `registry-projects-review` exposes
Registryctl's complete redacted acquisition and disclosure explanation when a
reviewer needs more detail than the concise default report. Release-pin review
now also rejects a Registryctl version that does not match the selected
Registry Stack tag. Runtime staging consumes Registryctl's versioned JSON build
report and validates its project-owned output root instead of constructing a
private compiler path. Hosted Notary profiles now inherit the product's 128 MiB
CEL worker default; the 1 GiB override remains limited to emulated local runs.

The NIA eSignet profile remains explicit beta functionality. Solmara now
builds its Relay runtime from the exact v0.13.0 source commit with only the
required `attribute-release` feature, using the published Relay image as its
runtime base. The release-candidate workflow publishes that source-bound
runtime before the hosted wrapper. PostgreSQL health checks now probe the TCP
server, preventing bootstrap jobs from racing PostgreSQL's temporary
initialization server on a fresh volume.

## 2026-07-16 Registry Stack v0.10.0 adoption

The lab now uses the authenticated Relay and Notary image digests and
Registryctl binary from the Registry Stack `v0.10.0` beta release. The release
keeps the implementer-facing pin surface in `versions.env` while preserving one
PostgreSQL-backed Notary per Relay authority across local and hosted topology
definitions.

## 2026-07-15 Authority-owned Notary topology

The lab now runs exactly six authority-owned Relay and Notary pairs: CRA, NIA,
SRO, Programme, SIPF, and NAgDI. Each Notary owns an isolated PostgreSQL
database and shares a loopback network boundary with its authority Relay. The
purpose-specific citizen, issuer, child-benefit, and pension Notary topology is
retired. Registry Notary no longer uses production Redis; eSignet continues to
use its own Redis service. Local PostgreSQL now mounts its named volume directly
at the PostgreSQL 16 data directory so `just down` and `just up` preserve all
authority correctness state. The release-candidate smoke proves the PostgreSQL
system identity and every authority's nonempty correctness state survive that
exact lifecycle, while rejecting anonymous PGDATA mounts.
Local eSignet now exposes its issuer port through the same standards edge used
by hosted deployments, so root discovery and `/v1/esignet` share the public
issuer origin while the Java backend remains internal. The NIA UserInfo release
profile now resolves eSignet's `individual_id` input against the canonical UIN
column, matching the portal login identifier and returning the typed identity
claims from the authority source.

## 2026-07-05 Visitor's Center completion pass

The visitor center gained its full set of reference pages and a topology-wide
trust strip. The explorer now renders the entire published metadata surface
(api-catalog, DCAT datasets, CPSV-AP services, evidence offerings grouped by
authority, and ODRL policies), each entity with its semantics, a raw-artifact
link, and copy-as-curl. The purpose register and problem-code reference are
generated from the purpose catalogue and story metadata, and the anatomy page
links each ministry to its entire configuration in the repository. The trust
strip now probes the then-current topology (metadata, scenario runner, portal,
Relay, and Notary endpoints) with honest auth-gated semantics, reads the newest
smoke evidence, and shows the generated data seed from the generator output. The
engineer door publishes the synthetic demo tokens through a server-side
allowlist alongside copy-as-curl examples, including the skeptic's wrong-purpose
call. The citizen portal now accepts a persona handoff so a visitor lands as the
person named on the card.

## 2026-07-04 Solmara Lab baseline

The wave 1 topology, guided scenarios, citizen portal, and the first cut of the
visitor center landed as the Solmara Lab baseline.
