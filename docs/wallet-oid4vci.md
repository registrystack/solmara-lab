# Solmara Wallet And OID4VCI Issuer

Status: operator notes for the hosted Solmara wallet demo.

Solmara uses a separate Registry Notary as the OID4VCI issuer:

- Issuer: `https://citizen-issuer-notary.solmara.registrystack.org`
- Holder wallet: `https://wallet.solmara.registrystack.org`
- Authorization server: `https://esignet.solmara.registrystack.org`
- eSignet UI: `https://esignet-ui.solmara.registrystack.org`

The existing `citizen-notary` remains the portal BFF notary with API-key auth.
Do not switch it to OIDC for the wallet flow. The wallet issuer needs OIDC
self-attestation and its own OID4VCI endpoints, so it runs as
`citizen-issuer-notary`.

## Hosted Services

Deploy these apps for the hosted wallet flow:

| App | Compose file | Purpose |
|---|---|---|
| `solmara-lab-esignet` | `compose.coolify.esignet.yaml` | Registers the portal client and the `solmara-citizen-issuer` client. |
| `solmara-lab-citizen-services` | `compose.coolify.citizen-services.yaml` | Runs `citizen-notary` and `citizen-issuer-notary`. |
| `solmara-lab-wallet` | `compose.coolify.walt.yaml` | Runs the Walt holder wallet behind Caddy. |

The Walt compose app loads `config/walt/` from the deployed Git ref into named
volumes because Coolify does not seed bind mounts from the repository checkout.
Set `CONFIG_REPO_REF` to the commit SHA being deployed.

## Required Key Material

The issuer notary uses three private keys:

- `CITIZEN_ISSUER_NOTARY_ISSUER_JWK`: Ed25519 issuer key for the SD-JWT VC.
- `CITIZEN_ISSUER_NOTARY_ACCESS_TOKEN_JWK`: Ed25519 key for OID4VCI access tokens.
- `CITIZEN_ISSUER_ESIGNET_RP_JWK`: RSA key for eSignet `private_key_jwt`.

eSignet must be seeded with the matching PEM value:

- `CITIZEN_ISSUER_ESIGNET_CLIENT_PRIVATE_KEY_B64`

`scripts/gen-secrets.py` generates matching local values for the RSA private JWK
and PEM pair. For hosted deployment, generate or rotate the pair together.

## Smoke Verification

Run the full hosted smoke with the usual demo tokens available in `.env` or the
process environment:

```bash
just hosted-smoke
```

The wallet/OID4VCI section checks:

- `https://wallet.solmara.registrystack.org/` responds.
- `/.well-known/openid-credential-issuer` advertises
  `citizen_status_sd_jwt`.
- The VCT metadata resolves under
  `/.well-known/vct/credentials/citizen-status/v1`.
- `/oid4vci/credential-offer` returns an offer for the configured credential.
- Unknown credential configuration IDs are refused.
- `/oid4vci/nonce` issues a `c_nonce`.
- `/oid4vci/offer/start` redirects to the Solmara eSignet UI.
- `/oid4vci/credential` refuses unauthenticated requests.

Manual wallet flow:

1. Open `https://wallet.solmara.registrystack.org`.
2. Start issuance from
   `https://citizen-issuer-notary.solmara.registrystack.org/oid4vci/offer/start?credential_configuration_id=citizen_status_sd_jwt`.
3. Sign in through Solmara eSignet using a seeded Solmara persona and the demo
   OTP configured for the environment.
4. Accept the credential in the wallet.

If the issuer redirects back with an error, check eSignet client registration
first. The client id must be `solmara-citizen-issuer`, the key id must be
`solmara-citizen-issuer-key-1`, and the registered redirect URI must be
`https://citizen-issuer-notary.solmara.registrystack.org/oid4vci/offer/callback`.
