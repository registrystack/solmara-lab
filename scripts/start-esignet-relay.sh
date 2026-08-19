#!/bin/bash
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

keystore_path="${REGISTRY_ESIGNET_KYC_SIGNING_KEYSTORE_PATH:?missing REGISTRY_ESIGNET_KYC_SIGNING_KEYSTORE_PATH}"
keystore_password="${REGISTRY_ESIGNET_KYC_SIGNING_KEYSTORE_PASSWORD:?missing REGISTRY_ESIGNET_KYC_SIGNING_KEYSTORE_PASSWORD}"
key_alias="${REGISTRY_ESIGNET_KYC_SIGNING_KEY_ALIAS:?missing REGISTRY_ESIGNET_KYC_SIGNING_KEY_ALIAS}"
key_password="${REGISTRY_ESIGNET_KYC_SIGNING_KEY_PASSWORD:?missing REGISTRY_ESIGNET_KYC_SIGNING_KEY_PASSWORD}"

if [[ -n "${REGISTRY_TLS_CA_CERT:-}" ]]; then
  truststore=/tmp/registry-esignet-truststore.p12
  rm -f "$truststore"
  keytool -importcert -noprompt \
    -alias registry-runtime-ca \
    -file "$REGISTRY_TLS_CA_CERT" \
    -keystore "$truststore" \
    -storetype PKCS12 \
    -storepass changeit \
    >/dev/null
  export JAVA_TOOL_OPTIONS="${JAVA_TOOL_OPTIONS:-} -Djavax.net.ssl.trustStore=$truststore -Djavax.net.ssl.trustStorePassword=changeit"
fi

mkdir -p "$(dirname "$keystore_path")"

if [[ -f "$keystore_path" ]] && ! keytool -list \
  -keystore "$keystore_path" \
  -storetype PKCS12 \
  -storepass "$keystore_password" \
  -alias "$key_alias" \
  >/dev/null 2>&1; then
  rm -f "$keystore_path"
fi

if [[ ! -f "$keystore_path" ]]; then
  keytool -genkeypair \
    -alias "$key_alias" \
    -keyalg RSA \
    -keysize 2048 \
    -dname "CN=solmara-esignet-relay" \
    -validity 825 \
    -storetype PKCS12 \
    -keystore "$keystore_path" \
    -storepass "$keystore_password" \
    -keypass "$key_password" \
    -noprompt
fi

exec /home/mosip/configure_start.sh "$@"
