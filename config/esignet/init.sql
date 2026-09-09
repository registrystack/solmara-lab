CREATE DATABASE mosip_esignet;


\connect mosip_esignet

CREATE SCHEMA IF NOT EXISTS esignet;
ALTER DATABASE mosip_esignet SET search_path TO esignet, pg_catalog, public;

CREATE TABLE IF NOT EXISTS esignet.ca_cert_store (
  cert_id varchar(36) PRIMARY KEY,
  cert_subject varchar(500) NOT NULL,
  cert_issuer varchar(500) NOT NULL,
  issuer_id varchar(36) NOT NULL,
  cert_not_before timestamp,
  cert_not_after timestamp,
  crl_uri varchar(120),
  cert_data varchar(4000),
  cert_thumbprint varchar(100),
  cert_serial_no varchar(50),
  partner_domain varchar(36),
  cr_by varchar(256),
  cr_dtimes timestamp,
  upd_by varchar(256),
  upd_dtimes timestamp,
  is_deleted boolean DEFAULT false,
  del_dtimes timestamp,
  ca_cert_type varchar(25),
  UNIQUE (cert_thumbprint, partner_domain)
);

CREATE TABLE IF NOT EXISTS esignet.client_detail (
  id varchar(100) CONSTRAINT pk_clntdtl_id PRIMARY KEY,
  name varchar(600) NOT NULL,
  rp_id varchar(100) NOT NULL,
  logo_uri varchar(2048) NOT NULL,
  redirect_uris varchar(2048) NOT NULL,
  claims varchar(2048) NOT NULL,
  acr_values varchar(1024) NOT NULL,
  public_key varchar(1024) NOT NULL,
  public_key_hash varchar(128) NOT NULL CONSTRAINT uk_clntdtl_public_key_hash UNIQUE,
  enc_public_key varchar(1024),
  enc_public_key_hash varchar(128),
  enc_public_key_cert varchar(4000),
  grant_types varchar(512) NOT NULL,
  auth_methods varchar(512) NOT NULL,
  status varchar(20) NOT NULL,
  additional_config varchar(2048),
  cr_dtimes timestamp NOT NULL,
  upd_dtimes timestamp
);

CREATE TABLE IF NOT EXISTS esignet.consent_detail (
  id varchar(36) PRIMARY KEY,
  client_id varchar(256) NOT NULL,
  psu_token varchar(256) NOT NULL,
  claims varchar(2048) NOT NULL,
  authorization_scopes varchar(1024) NOT NULL,
  cr_dtimes timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL,
  expire_dtimes timestamp,
  signature varchar(1024),
  hash varchar(100),
  accepted_claims varchar(1024),
  permitted_scopes varchar(1024)
);

CREATE TABLE IF NOT EXISTS esignet.consent_history (
  id varchar(36) PRIMARY KEY,
  client_id varchar(256) NOT NULL,
  psu_token varchar(256) NOT NULL,
  claims varchar(2048) NOT NULL,
  authorization_scopes varchar(1024) NOT NULL,
  cr_dtimes timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL,
  expire_dtimes timestamp,
  signature varchar(1024),
  hash varchar(1024),
  accepted_claims varchar(1024),
  permitted_scopes varchar(1024)
);

CREATE TABLE IF NOT EXISTS esignet.key_alias (
  id varchar(36) PRIMARY KEY,
  app_id varchar(36) NOT NULL,
  ref_id varchar(128),
  key_gen_dtimes timestamp,
  key_expire_dtimes timestamp,
  status_code varchar(36),
  lang_code varchar(3),
  cr_by varchar(256) NOT NULL,
  cr_dtimes timestamp NOT NULL,
  upd_by varchar(256),
  upd_dtimes timestamp,
  is_deleted boolean DEFAULT false,
  del_dtimes timestamp,
  cert_thumbprint varchar(100),
  uni_ident varchar(50)
);

CREATE TABLE IF NOT EXISTS esignet.key_policy_def (
  app_id varchar(36) PRIMARY KEY,
  key_validity_duration smallint,
  is_active boolean NOT NULL,
  pre_expire_days smallint,
  access_allowed varchar(1024),
  cr_by varchar(256) NOT NULL,
  cr_dtimes timestamp NOT NULL,
  upd_by varchar(256),
  upd_dtimes timestamp,
  is_deleted boolean DEFAULT false,
  del_dtimes timestamp
);

CREATE TABLE IF NOT EXISTS esignet.key_store (
  id varchar(36) PRIMARY KEY,
  master_key varchar(36) NOT NULL,
  private_key varchar(2500) NOT NULL,
  certificate_data varchar(4000) NOT NULL,
  cr_by varchar(256) NOT NULL,
  cr_dtimes timestamp NOT NULL,
  upd_by varchar(256),
  upd_dtimes timestamp,
  is_deleted boolean DEFAULT false,
  del_dtimes timestamp
);

CREATE TABLE IF NOT EXISTS esignet.public_key_registry (
  id_hash varchar(100) PRIMARY KEY,
  auth_factor varchar(25) NOT NULL,
  psu_token varchar(256) NOT NULL,
  public_key varchar(2500) NOT NULL,
  expire_dtimes timestamp NOT NULL,
  wallet_binding_id varchar(256) NOT NULL,
  public_key_hash varchar(100) NOT NULL,
  certificate varchar(4000) NOT NULL,
  cr_dtimes timestamp NOT NULL,
  thumbprint varchar(128) NOT NULL
);

CREATE TABLE IF NOT EXISTS esignet.server_profile (
  profile_name varchar(100) NOT NULL,
  feature varchar(100) NOT NULL,
  additional_config_key varchar(200) NOT NULL,
  PRIMARY KEY (profile_name, feature)
);

INSERT INTO esignet.key_policy_def (
  app_id, key_validity_duration, is_active, pre_expire_days, access_allowed,
  cr_by, cr_dtimes, is_deleted
) VALUES
  ('BASE', 1095, true, 50, 'NA', 'mosipadmin', now(), false),
  ('OIDC_PARTNER', 1095, true, 50, 'NA', 'mosipadmin', now(), false),
  ('OIDC_SERVICE', 1095, true, 50, 'NA', 'mosipadmin', now(), false),
  ('ROOT', 2920, true, 1125, 'NA', 'mosipadmin', now(), false)
ON CONFLICT (app_id) DO NOTHING;

INSERT INTO esignet.server_profile (
  profile_name, feature, additional_config_key
) VALUES
  ('fapi2.0', 'PAR', 'require_pushed_authorization_requests'),
  ('fapi2.0', 'DPOP', 'dpop_bound_access_tokens'),
  ('fapi2.0', 'PKCE', 'require_pkce')
ON CONFLICT (profile_name, feature) DO NOTHING;


ALTER TABLE esignet.consent_detail ADD CONSTRAINT unique_client_token UNIQUE (client_id, psu_token);
CREATE UNIQUE INDEX key_alias_uni_ident ON esignet.key_alias (uni_ident);
