ARG ESIGNET_UI_IMAGE=mosipid/oidc-ui:1.8.0
FROM ${ESIGNET_UI_IMAGE}

ARG ESIGNET_NGINX_CONF=config/esignet/nginx-hosted.conf
COPY ${ESIGNET_NGINX_CONF} /etc/nginx/nginx.conf
