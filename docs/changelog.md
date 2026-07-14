# Solmara Lab Changelog

A small dated log of what changed in the visitor center and the lab topology.
Newest entry first.

## 2026-07-15 Authority-owned Notary topology

The lab now runs exactly six authority-owned Relay and Notary pairs: CRA, NIA,
SRO, Programme, SIPF, and NAgDI. Each Notary owns an isolated PostgreSQL
database and shares a loopback network boundary with its authority Relay. The
purpose-specific citizen, issuer, child-benefit, and pension Notary topology is
retired. Registry Notary no longer uses production Redis; eSignet continues to
use its own Redis service.

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
