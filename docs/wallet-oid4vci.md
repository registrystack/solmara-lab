# Retired wallet issuer topology

Status: retired before Registry Stack 1.0.

The former citizen-services deployment added a portal Notary and a separate
OpenID for Verifiable Credential Issuance (OID4VCI) Notary. That
purpose-specific model is not part of the clean Solmara topology. Do not deploy
`citizen-notary`, `citizen-issuer-notary`, or the removed
`compose.coolify.citizen-services.yaml` application.

Solmara now runs exactly six authority-owned Relay and Notary pairs: CRA, NIA,
SRO, Programme, SIPF, and NAgDI. Citizen portal journeys use evidence exposed
by those authority Notaries. Adding a credential issuance journey must extend
the owning authority project rather than create a purpose-specific Notary.

The Walt holder wallet application remains available as an isolated UI
demonstrator through `compose.coolify.walt.yaml`, but the current six-authority
topology does not expose an OID4VCI issuer. eSignet remains the portal identity
provider, and its Redis service remains eSignet-owned state.
