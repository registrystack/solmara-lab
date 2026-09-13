#!/bin/sh
# Compatibility launcher for operators of the native eSignet v2 image.
set -eu
: "${REGISTRY_ESIGNET_CONFIG_FILE:?set the native provider YAML path}"
: "${KEYMANAGER_PKCS12_PASSWORD:?set the eSignet host keystore password}"
exec /home/mosip/esignet "$@"
