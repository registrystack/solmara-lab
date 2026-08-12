# Solmara Lab hosted deployment

Status: migration runbook. It does not claim that a hosted environment runs
this branch.

## Current deployment boundary

The active architecture uses six authority-owned Registry Relay Records APIs,
one centralized Registry Evidence service, and Registry Mint. Registry Notary
is retired and must not be deployed from historical Solmara configuration.

Registry Stack v0.18.0 supplies the published Relay image and the released
Evidence, Evidencectl, Mint, and Registryctl binaries consumed by this lab.
`versions.env` binds their release tag, source commit, checksums, and image
references.

The public Solmara hostnames are deployment targets only. Repository contents
do not prove that a target is deployed or reachable. A hosted promotion is
complete only after the selected Coolify Compose files validate, the exact
revision is deployed, and the hosted smoke passes.

## Intended service topology

| Service | Intended endpoint |
|---|---|
| Visitor Center | `https://solmara.registrystack.org` |
| Citizen portal | `https://portal.solmara.registrystack.org` |
| Registry Evidence | `https://evidence.solmara.registrystack.org` |
| Registry Mint | `https://mint.solmara.registrystack.org` |
| Static metadata | `https://metadata.solmara.registrystack.org` |
| CRA Records API | `https://cra-relay.solmara.registrystack.org` |
| NIA Records API | `https://nia-relay.solmara.registrystack.org` |
| SRO Records API | `https://sro-relay.solmara.registrystack.org` |
| Programme Records API | `https://mosd-programme-relay.solmara.registrystack.org` |
| SIPF Records API | `https://sipf-relay.solmara.registrystack.org` |
| NAgDI Records API | `https://nagdi-relay.solmara.registrystack.org` |
| eSignet | `https://esignet.solmara.registrystack.org` |
| eSignet UI | `https://esignet-ui.solmara.registrystack.org` |
| Walt holder wallet | `https://wallet.solmara.registrystack.org` |

The six Relay services expose protected Records APIs. Evidence calls them with
short-lived, source-scoped workload credentials. Mint issues the application
token used to call `POST /v1/evidence`; Evidence authenticates that token,
applies the selected requirement and purpose, and returns a signed,
minimum-disclosure assertion.

## Promotion requirements

1. Confirm every Registry Stack reference resolves to the v0.18.0 release
   identity recorded in `versions.env`.
2. Use digest-pinned images in Coolify. Do not promote mutable tags.
3. Provide only the secrets referenced by each selected Compose file. Keep
   private keys, bearer tokens, and database URLs out of logs and commits.
4. Validate the selected Compose configuration and generated Relay runtime.
5. Deploy the authority Records APIs before Evidence, Mint, and edge services.
6. Run `just hosted-smoke` against the deployed revision. If the migration has
   not yet supplied that command with a complete Evidence path, stop rather
   than treating an older smoke as proof.

## Verification

A hosted verification must cover:

- readiness for all six Relay services, Evidence, Mint, metadata, and the edge
  applications;
- one authenticated `GET /v1/evidence-definitions` discovery request;
- representative signed Evidence requests for child benefit, pension,
  survivor benefit, farmer voucher, and livestock movement requirements;
- a wrong-purpose denial that reveals no protected source value;
- verification of an Evidence response with the pinned public key set; and
- portal and Visitor Center flows against the same deployed revision.

Do not reuse the retired per-authority evaluation routes, Notary databases,
consultation Relay lanes, or Notary workload identities as part of this
migration.
