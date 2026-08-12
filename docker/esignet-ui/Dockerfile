ARG ESIGNET_UI_IMAGE=mosipid/oidc-ui@sha256:8a2a6839b4e22be6c967dabc6308190c165c54604a778c2d9b1aae8091db93e7
FROM ${ESIGNET_UI_IMAGE}

ARG ESIGNET_NGINX_CONF=config/esignet/nginx-hosted.conf
COPY ${ESIGNET_NGINX_CONF} /etc/nginx/nginx.conf
