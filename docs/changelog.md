# Solmara Lab Changelog

A small dated log of what changed in the visitor center and the lab topology.
Newest entry first.

## 2026-08-21 The local front door is `local-edge`

The local Compose service that terminates TLS on port 4341 was called
`evidence-gateway`, which now names something else. It is also not only an
Evidence front door: the same Caddy instance answers the Relay and Mint
hostnames the hermetic local run needs. It is now `local-edge`, pinned by
`LOCAL_EDGE_IMAGE`, and its published port is `SOLMARA_LOCAL_EDGE_PORT`. The
default port is still 4341, so a developer who never overrode
`SOLMARA_EVIDENCE_GATEWAY_PORT` has nothing to change. Nothing hosted uses
this service.

## 2026-08-20 Evidence gateways replace "cells"

Every visitor-facing surface now calls an authority's Evidence deployment an
Evidence gateway. "Cell" was a private coinage of the reset and was never
defined for a reader; "gateway" is the noun Registry Stack itself uses for the
service that answers a requirement over an authority's own source. Nothing in
the topology changed. Directory names, hostnames, volume paths, and the
`solmara-authority-cells` catalogue identifier keep their existing spelling
because they are identities rather than descriptions.

## 2026-08-20 Registry Stack v0.23.0

Solmara pins Registry Stack v0.23.0 across `versions.env`, the release-pin
gate, and the home release-identity surface. The Relay, Evidence, and Mint OCI
references move to the v0.23.0 digests, and the Relayctl authoring helper is
built from the v0.23.0 `linux-amd64` release asset and its checksum. The
topology is unchanged. The reason to move is security: v0.23.0 upgrades `h2`
to 0.4.17, past RUSTSEC-2026-0258, where a peer could queue unlimited empty
DATA frames on the HTTP/2 path that Relay and Evidence both serve over.

The Evidence deployment contract gained three required fields, so the six gateway
bundles are authored rather than only re-pinned. `service.publicOrigin` names
the one routed origin RFC 9728 discovery answers on, which is each gateway's own
`<authority>-evidence.solmara.registrystack.org`. Every requirement and every
concept now carries a `handle`, the stable key a client reads a result under;
each is authored to the last segment of the identifier it names. v0.23.0 also
adds Registry Discovery and published Discovery client packages, neither of
which the lab uses yet.

Because the Evidence bundle content changed, the staged runtime a deployment
already holds no longer matches the one this version stages. A local run needs
`just reset` before `just up`. A hosted rollout cannot reuse the existing
Evidence and Relay runtime volumes.

## 2026-08-19 Registry Stack v0.22.0

Solmara pins Registry Stack v0.22.0 across `versions.env`, the release-pin
gate, and the home release-identity surface. The Relay, Evidence, and Mint OCI
references move to the v0.22.0 digests, and the Relayctl authoring helper is
built from the v0.22.0 `linux-amd64` release asset and its checksum. The
topology is unchanged; v0.22.0 adds a container runtime deployment preflight,
a strict Mint readiness probe, Mint support for compatible OAuth clients,
eager validation of Evidence trusted public keys, and root-owned Relay
configuration.

## 2026-08-13 Official Registry Stack runtime images

Solmara no longer assembles or publishes local Evidence and Mint runtime
wrappers. Relay, Evidence, and Mint are now closed to their official Registry
Stack v0.21.0 GHCR repositories and immutable digests from `versions.env`;
only the Relayctl authoring helper is assembled locally from a
checksum-verified release asset. The release-candidate handoff carries the
upstream Evidence and Mint
references unchanged and publishes only Solmara-owned deployment images. Relay
now follows the same closed handoff: hosted Compose consumes the canonical
`REGISTRY_RELAY_IMAGE` reference rather than rebuilding it from a separate
digest input.

## 2026-08-12 Authority-owned Relay and Evidence reset

Solmara now authors six independent Evidence gateways and five Relay V2 projects.
CRA, NIA, and SRO publish immutable SQLite extracts for direct Evidence use;
CRA, MoSD, SIPF, and NAgDI expose only named exact Relay lookups, with NIA's
Relay reserved for the optional eSignet UserInfo profile. The programme code
routes all 11 preserved requirements to their owning authority, verifies each
ES256 JWS against that authority's JWKS, and composes application outcomes.

The reset replaces the old singleton Evidence, Records API, ambient purpose
header, and authority decision-service topology. Mutable Relay publications and
versioned immutable extracts now have deliberately different lifecycle proof.
Registry Stack v0.19.0 was found incapable of issuing Relay-compatible Mint
claims and of representing Relay's concealed unresolved outcome in Evidence
fixtures. v0.20.1 added those capabilities but did not publish official
Evidence and Mint images. The completed reset therefore pins Registry Stack
v0.21.0 by exact release source, Relayctl checksum, and official Relay,
Evidence, and Mint OCI digests. The separately released
`esignet-relay-authenticator` v0.2.0 JAR is pinned by SHA-256.

## 2026-08-06 Registry Stack main Evidence migration

The local lab now builds Relay, Registry Evidence, and Registry Mint from the
exact Registry Stack `main` commit pinned in `versions.env`. Six authority
Relays expose current Records APIs to one Evidence service through scoped,
short-lived workload credentials. Mint uses `private_key_jwt` client
authentication, and the application journeys consume flattened signed JWS
Evidence assertions instead of authority Notary evaluations.

All six Registry projects and their committed runtime closures are regenerated
with Registryctl 0.17.0. Eleven Evidence requirements cover child benefit,
pension and survivor workflows, farmer and livestock controls, and citizen
self-service. The active local quality gates validate the paired Mint config,
the Evidence bundle, and 89 Evidence fixture cases. Hosted and Coolify files
remain on the earlier released Notary topology and are explicitly unsupported
on this source-only branch.

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
