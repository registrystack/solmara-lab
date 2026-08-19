# Solmara Lab API workspace

The examples exercise the authority-owned reset:

1. The child-benefit programme composes four independently signed assertions.
2. CRA and SIPF issue separate pension and survivor assertions.
3. NAgDI issues separate voucher and livestock assertions.
4. The Relay V2 folder demonstrates only the eight governed exact lookups used
   by Evidence and the optional NIA eSignet profile.

Set `EVIDENCE_ACCESS_TOKEN` to a short-lived Registry Mint token for the
authority Evidence endpoints. Set `CHILD_BENEFIT_FEDERATOR_TOKEN` only when
calling the programme application. Purpose is part of each Evidence request or
programme request body. It is not an ambient HTTP header.

Each Relay request uses a different placeholder token variable because Mint
fixes the scope and purpose claim per client. The example selectors identify
synthetic lab fixtures only. Relay responses remain no-store and disclose only
the explicitly requested governed fields.

Every direct Evidence response is a flattened ES256 JWS. Verify it against the
JWKS of the authority host that received the request. The examples contain no
real-person selector, token value, source row, private audit data, or signing
key.

The fixed request nonces are readable examples. Replace each one with 32 random
bytes encoded as unpadded base64url before using the collection outside the lab.
