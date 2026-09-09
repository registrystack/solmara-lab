# syntax=docker/dockerfile:1
ARG NODE_BUILD_IMAGE
ARG ESIGNET_NGINX_IMAGE
FROM ${NODE_BUILD_IMAGE} AS ui-build
ARG ESIGNET_SOURCE_COMMIT
ARG ESIGNET_SOURCE_ARCHIVE_SHA256
WORKDIR /src
ADD --checksum=sha256:${ESIGNET_SOURCE_ARCHIVE_SHA256} https://api.github.com/repos/mosip/esignet/tarball/${ESIGNET_SOURCE_COMMIT} /tmp/esignet.tar.gz
RUN tar -xzf /tmp/esignet.tar.gz --strip-components=1 && rm /tmp/esignet.tar.gz
COPY docker/esignet-ui/default-locale.patch /tmp/default-locale.patch
RUN apk add --no-cache git && git apply --check /tmp/default-locale.patch && git apply /tmp/default-locale.patch
WORKDIR /src/oidc-ui
RUN npm ci && VITE_API_URL= npm run build

FROM ${ESIGNET_NGINX_IMAGE}
ARG ESIGNET_SOURCE_COMMIT
LABEL org.opencontainers.image.revision=${ESIGNET_SOURCE_COMMIT} \
      org.opencontainers.image.version="2.0.0-beta.1"
ARG ESIGNET_NGINX_CONF=config/esignet/nginx-hosted.conf
COPY --from=ui-build /src/oidc-ui/dist /usr/share/nginx/html
COPY ${ESIGNET_NGINX_CONF} /etc/nginx/solmara.conf.template
COPY docker/esignet-ui/render-hosted-nginx.sh /usr/local/bin/render-hosted-nginx.sh
COPY docker/esignet-ui/hosted-entrypoint.sh /usr/local/bin/hosted-entrypoint.sh
RUN chmod 0555 /usr/local/bin/*nginx.sh /usr/local/bin/hosted-entrypoint.sh
USER 101:101
ENTRYPOINT ["/usr/local/bin/hosted-entrypoint.sh"]
CMD ["nginx", "-c", "/tmp/solmara-nginx.conf", "-g", "daemon off;"]
