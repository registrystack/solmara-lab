# Solmara Lab Changelog

A small dated log of what changed in the visitor center and the lab topology.
Newest entry first.

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
