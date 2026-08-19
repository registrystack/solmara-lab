# SPDX-License-Identifier: Apache-2.0

ARG ESIGNET_BASE_IMAGE=mosipid/esignet-with-plugins@sha256:47fffdb5a45198b29885a533841129877a7385a12bcb6020c0f6d4335477be39
ARG ESIGNET_AUTHENTICATOR_JAR_URL
ARG ESIGNET_AUTHENTICATOR_JAR_SHA256

FROM alpine@sha256:d9e853e87e55526f6b2917df91a2115c36dd7c696a35be12163d44e6e2a4b6bc AS authenticator
ARG ESIGNET_AUTHENTICATOR_JAR_URL
ARG ESIGNET_AUTHENTICATOR_JAR_SHA256
RUN test -n "$ESIGNET_AUTHENTICATOR_JAR_URL" && \
    test -n "$ESIGNET_AUTHENTICATOR_JAR_SHA256" && \
    wget -q -O /esignet-relay-authenticator.jar "$ESIGNET_AUTHENTICATOR_JAR_URL" && \
    printf '%s  %s\n' "$ESIGNET_AUTHENTICATOR_JAR_SHA256" /esignet-relay-authenticator.jar | sha256sum -c -

FROM ${ESIGNET_BASE_IMAGE}

COPY --from=authenticator /esignet-relay-authenticator.jar /home/mosip/plugins/esignet-relay-authenticator.jar
COPY scripts/start-esignet-relay.sh /usr/local/bin/start-esignet-relay.sh

USER root
RUN chmod 0755 /usr/local/bin/start-esignet-relay.sh && \
    chown root:root /usr/local/bin/start-esignet-relay.sh && \
    chown mosip:mosip /home/mosip/plugins/esignet-relay-authenticator.jar

ENTRYPOINT ["/usr/local/bin/start-esignet-relay.sh"]
CMD ["java", "-jar", "-Dloader.path=${loader_path_env}", "-Dspring.cloud.config.label=${spring_config_label_env}", "-Dspring.profiles.active=${active_profile_env}", "-Dspring.cloud.config.uri=${spring_config_url_env}", "esignet-service.jar"]
