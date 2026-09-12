#!/bin/sh
set -eu
/usr/local/bin/render-hosted-nginx.sh /etc/nginx/solmara.conf.template /tmp/solmara-nginx.conf
exec "$@"
