#!/bin/sh
set -eu

/home/mosip/render-hosted-nginx.sh \
  /home/mosip/nginx-hosted.conf.template \
  /tmp/solmara-nginx.conf

exec sh /home/mosip/configure-ui.sh "$@"
