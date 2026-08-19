ARG ESIGNET_UI_IMAGE=mosipid/oidc-ui@sha256:8a2a6839b4e22be6c967dabc6308190c165c54604a778c2d9b1aae8091db93e7
FROM ${ESIGNET_UI_IMAGE}

ARG ESIGNET_NGINX_CONF=config/esignet/nginx-hosted.conf
COPY ${ESIGNET_NGINX_CONF} /home/mosip/nginx-hosted.conf.template
COPY docker/esignet-ui/render-hosted-nginx.sh /home/mosip/render-hosted-nginx.sh
COPY docker/esignet-ui/hosted-entrypoint.sh /home/mosip/hosted-entrypoint.sh

USER root
RUN mv /home/mosip/configure_start.sh /home/mosip/configure-ui.sh && \
    chmod 0555 /home/mosip/configure-ui.sh \
      /home/mosip/render-hosted-nginx.sh \
      /home/mosip/hosted-entrypoint.sh && \
    chmod 0444 /home/mosip/nginx-hosted.conf.template
USER 1001:1001

ENTRYPOINT ["/home/mosip/hosted-entrypoint.sh"]
CMD ["nginx", "-c", "/tmp/solmara-nginx.conf", "-g", "daemon off;"]
