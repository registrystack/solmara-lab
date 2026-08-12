# Wallet and OID4VCI status

Status: holder demonstrator only.

Registry Stack v0.18.0 includes an Evidence OpenID for Verifiable Credential
Issuance (OID4VCI) adapter. Solmara Lab does not currently configure or deploy
that adapter. The active application journeys request audience-scoped signed
Evidence directly from the centralized Evidence service.

The former citizen-services deployment used purpose-specific Notary services.
That retired model is not part of the current topology. Do not deploy
`citizen-notary`, `citizen-issuer-notary`, or the removed
`compose.coolify.citizen-services.yaml` application.

The Walt holder wallet application remains available as an isolated UI
demonstrator through `compose.coolify.walt.yaml`. It is not proof of an issuer
integration and the current Solmara topology does not expose an OID4VCI issuer.
Any future wallet delivery must use the Registry Evidence OID4VCI adapter,
retain Evidence as the signer, and add an end-to-end holder-bound verification
journey. eSignet remains the portal identity provider, and its Redis service
remains eSignet-owned state.
