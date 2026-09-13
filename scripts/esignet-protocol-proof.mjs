#!/usr/bin/env node

// Exercise the candidate's real browser, provider, token endpoint and UserInfo.
// Ephemeral private keys and credentials stay in memory. Output is fixed labels.
// Run: node --experimental-strip-types scripts/esignet-protocol-proof.mjs
// Requires the running local fixture and installed portal dependencies/browser.
// ESIGNET_PROOF_ISSUER, ESIGNET_PROOF_PORT and ESIGNET_PROOF_CWD override local
// defaults. ESIGNET_PROOF_COMPOSE_ARGS_JSON is an array of docker compose options,
// including any --env-file paths. ESIGNET_DEMO_SUBJECT/OTP select the seeded login.
// Test clients use fresh IDs on each run; their private keys are never persisted.
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { writeFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { randomUUID } from 'node:crypto';
import { spawn } from 'node:child_process';
import { resolve } from 'node:path';
import * as oidc from '../portal/node_modules/openid-client/build/index.js';
import { chromium } from '../portal/node_modules/@playwright/test/index.mjs';
import { requestEsignetOtp, verifyEsignetOtp } from '../portal/e2e/support/auth.ts';

const requireOidc = createRequire(import.meta.resolve('../portal/node_modules/openid-client/build/index.js'));
const jose = await import(pathToFileURL(requireOidc.resolve('jose')).href);
const root = fileURLToPath(new URL('..', import.meta.url));
const claimNames = ['individual_id', 'name', 'given_name', 'family_name', 'gender', 'birthdate'];
const proofTrace = [];
const resultPath = '/tmp/solmara-esignet-protocol-proof.json';
const protocolClaims = new Set(['sub', 'iss', 'aud', 'iat', 'exp', 'nbf', 'jti']);
const grantFailureDescriptions = new Set(['Invalid authorization code', 'code_verifier is required',
  'Invalid code verifier', 'Invalid redirect URI', 'Expired authorization code']);

export function assertDisclosure(claims, expected, subject) {
  assert.ok(claims && typeof claims === 'object' && !Array.isArray(claims));
  assert.equal(typeof claims.sub, 'string');
  assert.ok(claims.sub.length > 0);
  if (subject) assert.equal(claims.sub, subject);
  assert.deepEqual(Object.keys(claims).filter((name) => !protocolClaims.has(name)).sort(), [...expected].sort());
  for (const name of expected) assert.ok(claims[name] !== null && claims[name] !== undefined);
}

export function validateCallback(url, pending) {
  assert.equal(url.origin, new URL(pending.redirectUri).origin);
  assert.equal(url.pathname, '/callback');
  assert.equal(url.searchParams.getAll('state').length, 1);
  assert.equal(url.searchParams.get('state'), pending.state);
  assert.equal(url.searchParams.has('code') !== url.searchParams.has('error'), true);
  if (url.searchParams.has('code')) assert.equal(url.searchParams.getAll('code').length, 1);
  return url;
}

export function registration(clientId, signingJwk, encryptionJwk, redirectUri) {
  return {
    clientId, clientName: 'Solmara Protocol Proof', clientNameLangMap: { eng: 'Solmara Protocol Proof' }, relyingPartyId: 'solmara',
    logoUri: 'https://id.registrystack.org/solmara/logo.svg', redirectUris: [redirectUri],
    userClaims: claimNames, authContextRefs: ['mosip:idp:acr:static-code'],
    publicKey: signingJwk, ...(encryptionJwk ? { encPublicKey: encryptionJwk } : {}),
    grantTypes: ['authorization_code'], clientAuthMethods: ['private_key_jwt'],
    additionalConfig: { userinfo_response_type: encryptionJwk ? 'JWE' : 'JWS',
      require_pkce: true, pkce_required: true }
  };
}

async function registerClient(payload) {
  // Explicit argument arrays avoid shell interpolation. Only public registration
  // material crosses stdin into the private Docker network.
  const composeArgs = JSON.parse(process.env.ESIGNET_PROOF_COMPOSE_ARGS_JSON || JSON.stringify([
    '-p', 'solmara-esignet-v2-fixture', '--env-file', 'versions.env', '--env-file', '.env',
    '-f', 'compose.esignet-fixture.yaml'
  ]));
  assert.ok(Array.isArray(composeArgs) && composeArgs.every((arg) => typeof arg === 'string'));
  const python = [
    'import json,sys,urllib.request,datetime',
    'payload=json.load(sys.stdin)',
    'body=json.dumps({"requestTime":datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00","Z"),"request":payload}).encode()',
    'request=urllib.request.Request("http://esignet:8080/client-mgmt/client",data=body,headers={"Content-Type":"application/json"})',
    'result=json.load(urllib.request.urlopen(request,timeout=20))',
    'sys.exit(0 if not result.get("errors") and result.get("response",{}).get("clientId")==payload["clientId"] else 1)'
  ].join('\n');
  await new Promise((resolveRun, rejectRun) => {
    const child = spawn('docker', ['compose', ...composeArgs, 'run', '--rm', '-T', '--no-deps',
      '--entrypoint', 'python', 'esignet-seed', '-c', python], {
      cwd: process.env.ESIGNET_PROOF_CWD || root, stdio: ['pipe', 'ignore', 'ignore']
    });
    const timeout = setTimeout(() => { child.kill(); rejectRun(new Error('registration timed out')); }, 60_000);
    child.on('error', () => { clearTimeout(timeout); rejectRun(new Error('registration failed')); });
    child.on('close', (code) => { clearTimeout(timeout); code === 0 ? resolveRun() : rejectRun(new Error('registration failed')); });
    child.stdin.end(JSON.stringify(payload));
  });
}

async function createClient(issuer, redirectUri, encrypted, onStage, acr = 'mosip:idp:acr:static-code') {
  const signing = await jose.generateKeyPair('RS256', { extractable: true });
  const signingJwk = { ...await jose.exportJWK(signing.publicKey), kid: randomUUID(), use: 'sig', alg: 'RS256' };
  const encryption = encrypted ? await jose.generateKeyPair('RSA-OAEP-256') : undefined;
  const encryptionJwk = encryption ? { ...await jose.exportJWK(encryption.publicKey), kid: randomUUID(), use: 'enc', alg: 'RSA-OAEP-256' } : undefined;
  const clientId = `solmara-proof-${encrypted ? 'jwe' : 'jws'}-${randomUUID().slice(0, 8)}`;
  onStage(encrypted ? 'encrypted-client-registration' : 'signed-client-registration');
  const payload = registration(clientId, signingJwk, encryptionJwk, redirectUri);
  payload.authContextRefs = [acr];
  await registerClient(payload);
  onStage(encrypted ? 'encrypted-client-discovery' : 'signed-client-discovery');
  const config = await oidc.discovery(new URL(issuer), clientId, {
    token_endpoint_auth_method: 'private_key_jwt', id_token_signed_response_alg: 'PS256',
    ...(encrypted ? {} : { userinfo_signed_response_alg: 'PS256' })
  }, oidc.PrivateKeyJwt({ key: signing.privateKey, kid: signingJwk.kid }), {
    execute: [oidc.enableNonRepudiationChecks, ...(issuer.startsWith('http:') ? [oidc.allowInsecureRequests] : [])],
    timeout: 15
  });
  assert.equal(config.serverMetadata().issuer, issuer);
  return { config, encryption, encryptionJwk, redirectUri, clientId, acr };
}

async function beginLogin(browser, client, claims, callbacks) {
  const context = await browser.newContext();
  const page = await context.newPage();
  page.setDefaultTimeout(20_000);
  page.on('response', async (response) => {
    const path = new URL(response.url()).pathname;
    if (!path.endsWith('/flow/execute')) return;
    try {
      const body = await response.json();
      proofTrace.push({ path, status: response.status(), flowStatus: body.flowStatus,
        errorCode: body.error?.code, fieldErrorCount: body.data?.fieldErrors?.length || 0 });
    } catch { /* Diagnostic metadata must not change proof behavior. */ }
  });
  const state = oidc.randomState();
  const nonce = oidc.randomNonce();
  const verifier = oidc.randomPKCECodeVerifier();
  const pending = { state, nonce, verifier, redirectUri: client.redirectUri };
  let receive;
  const callback = new Promise((resolveCallback) => { receive = resolveCallback; });
  callbacks.set(state, receive);
  const authorize = oidc.buildAuthorizationUrl(client.config, {
    redirect_uri: client.redirectUri, scope: 'openid', ui_locales: 'en', acr_values: client.acr, state, nonce,
    claims: JSON.stringify({ userinfo: claims }),
    code_challenge: await oidc.calculatePKCECodeChallenge(verifier), code_challenge_method: 'S256'
  });
  await page.goto(authorize.href);
  await page.waitForURL((url) => url.pathname === '/signin');
  return { page, context, pending, callback,
    close: async () => { callbacks.delete(state); await context.close(); } };
}

async function authenticate(flow, invalidOtp = false) {
  await requestEsignetOtp(flow.page);
  const otp = process.env.ESIGNET_DEMO_OTP || '111111';
  const response = await verifyEsignetOtp(flow.page, invalidOtp ? (otp === '000000' ? '999999' : '000000') : otp);
  const body = await response.json();
  if (invalidOtp) {
    assert.equal(response.status(), 200);
    assert.equal(body.flowStatus, 'INCOMPLETE');
    assert.equal(body.error?.code, 'FET-1005');
    assert.equal(await flow.page.getByRole('button', { name: 'Continue', exact: true }).count(), 0);
    assert.equal(new URL(flow.page.url()).pathname, '/signin');
    return;
  }
  assert.ok(response.ok() && body.flowStatus !== 'ERROR' && !body.error);
  await flow.page.getByRole('button', { name: 'Continue', exact: true }).waitFor();
}

async function chooseConsent(flow, allowed) {
  const toggles = flow.page.locator('input[type="checkbox"]');
  assert.ok(await toggles.count() > 0);
  for (let index = 0; index < await toggles.count(); index += 1) {
    const toggle = toggles.nth(index);
    const id = await toggle.getAttribute('id');
    if (id === 'consent_opt__all') continue;
    const matches = claimNames.filter((name) => id?.endsWith(`__${name}`));
    assert.equal(matches.length, 1);
    const label = matches[0];
    if (await toggle.isDisabled()) {
      assert.ok(allowed.includes(label));
      assert.ok(await toggle.isChecked());
    } else {
      const desired = allowed.includes(label);
      if (await toggle.isChecked() !== desired) await toggle.locator('xpath=..').click();
      assert.equal(await toggle.isChecked(), desired);
    }
  }
}

async function callbackFor(flow) {
  let timer;
  try {
    const url = await Promise.race([flow.callback, new Promise((_, rejectTimeout) => {
      timer = setTimeout(() => rejectTimeout(new Error('callback timeout')), 20_000);
    })]);
    return validateCallback(url, flow.pending);
  } finally { clearTimeout(timer); }
}

async function continueConsent(flow, allowed) {
  await chooseConsent(flow, allowed);
  const [response] = await Promise.all([
    flow.page.waitForResponse((response) =>
      new URL(response.url()).pathname.endsWith('/flow/execute') && response.request().method() === 'POST'),
    flow.page.getByRole('button', { name: 'Continue', exact: true }).click()
  ]);
  const body = await response.json();
  assert.equal(response.status(), 200);
  return body;
}

async function finishLogin(flow, client, allowed) {
  const body = await continueConsent(flow, allowed);
  assert.ok(body.flowStatus !== 'ERROR' && !body.error);
  const callback = await callbackFor(flow);
  assert.equal(callback.searchParams.has('error'), false);
  const token = await oidc.authorizationCodeGrant(client.config, callback, {
    expectedState: flow.pending.state, expectedNonce: flow.pending.nonce,
    pkceCodeVerifier: flow.pending.verifier, idTokenExpected: true
  });
  assert.ok(token.claims()?.sub);
  return { token, callback };
}

async function signedClaims(client, token) {
  const first = await oidc.fetchUserInfo(client.config, token.access_token, token.claims().sub);
  const second = await oidc.fetchUserInfo(client.config, token.access_token, token.claims().sub);
  assertDisclosure(second, Object.keys(first).filter((name) => !protocolClaims.has(name)), first.sub);
  for (const name of Object.keys(first).filter((key) => !protocolClaims.has(key))) assert.deepEqual(second[name], first[name]);
  return first;
}

async function encryptedClaims(client, token) {
  const response = await fetch(client.config.serverMetadata().userinfo_endpoint, {
    headers: { authorization: `Bearer ${token.access_token}` }, redirect: 'error'
  });
  assert.equal(response.status, 200);
  assert.ok(response.headers.get('content-type')?.startsWith('application/jwt'));
  const compact = await response.text();
  assert.equal(compact.split('.').length, 5);
  const { plaintext, protectedHeader } = await jose.compactDecrypt(compact, client.encryption.privateKey, {
    keyManagementAlgorithms: ['RSA-OAEP-256'], contentEncryptionAlgorithms: ['A256GCM']
  });
  assert.equal(protectedHeader.kid, client.encryptionJwk.kid);
  const claims = JSON.parse(new TextDecoder().decode(plaintext));
  assert.equal(claims.sub, token.claims().sub);
  const wrongRecipient = await jose.generateKeyPair('RSA-OAEP-256');
  await assert.rejects(() => jose.compactDecrypt(compact, wrongRecipient.privateKey));
  const parts = compact.split('.');
  parts[3] = (parts[3][0] === 'A' ? 'B' : 'A') + parts[3].slice(1);
  await assert.rejects(() => jose.compactDecrypt(parts.join('.'), client.encryption.privateKey));
  return claims;
}

export async function main() {
  const issuer = process.env.ESIGNET_PROOF_ISSUER || 'http://127.0.0.1:4308';
  const port = Number(process.env.ESIGNET_PROOF_PORT || 4315);
  const redirectUri = `http://127.0.0.1:${port}/callback`;
  const callbacks = new Map();
  const server = createServer((request, response) => {
    const url = new URL(request.url, redirectUri);
    const receive = callbacks.get(url.searchParams.get('state'));
    if (url.pathname === '/callback' && receive) {
      callbacks.delete(url.searchParams.get('state'));
      receive(url);
      response.writeHead(200, { 'content-type': 'text/plain', 'cache-control': 'no-store' });
      response.end('Protocol proof callback received.');
    } else { response.writeHead(404); response.end(); }
  });
  await new Promise((resolveListen, rejectListen) => {
    server.once('error', rejectListen);
    server.listen(port, '127.0.0.1', resolveListen);
  });
  let browser;
  let stage = 'registration';
  try {
    const signed = await createClient(issuer, redirectUri, false, (value) => { stage = value; });
    const encrypted = await createClient(issuer, redirectUri, true, (value) => { stage = value; });
    console.log('esignet-protocol-proof: client-registration PASS');
    browser = await chromium.launch({ headless: true });
    const requested = { individual_id: { essential: true }, given_name: null, name: null, gender: null };
    stage = 'invalid-otp';
    const invalid = await beginLogin(browser, signed, requested, callbacks);
    try { await authenticate(invalid, true); } finally { await invalid.close(); }
    console.log('esignet-protocol-proof: invalid-otp PASS');

    stage = 'essential-denial';
    const denied = await beginLogin(browser, signed, requested, callbacks);
    try {
      await authenticate(denied);
      const [response] = await Promise.all([
        denied.page.waitForResponse((response) =>
          new URL(response.url()).pathname.endsWith('/flow/execute') && response.request().method() === 'POST'),
        denied.page.getByRole('button', { name: 'Cancel', exact: true }).click()
      ]);
      const body = await response.json();
      assert.equal(response.status(), 200);
      assert.equal(body.flowStatus, 'ERROR');
      assert.equal(body.error?.code, 'FET-1066');
      assert.ok(callbacks.has(denied.pending.state));
      assert.equal(new URL(denied.page.url()).pathname, '/signin');
    } finally { await denied.close(); }
    console.log('esignet-protocol-proof: essential-denial PASS');

    stage = 'stronger-acr-refusal';
    const stronger = await createClient(issuer, redirectUri, false, () => {}, 'mosip:idp:acr:generated-code');
    const strongerFlow = await beginLogin(browser, stronger, requested, callbacks);
    try {
      await authenticate(strongerFlow);
      const body = await continueConsent(strongerFlow, ['individual_id', 'given_name']);
      assert.equal(body.flowStatus, 'ERROR');
      assert.equal(body.error?.code, 'FET-1082');
      assert.ok(callbacks.has(strongerFlow.pending.state));
      assert.equal(new URL(strongerFlow.page.url()).pathname, '/signin');
    } finally { await strongerFlow.close(); }
    console.log('esignet-protocol-proof: stronger-acr-refusal PASS');

    stage = 'signed-userinfo-optional-denial';
    const first = await beginLogin(browser, signed, requested, callbacks);
    let subject;
    try {
      await authenticate(first);
      const { token, callback } = await finishLogin(first, signed, ['individual_id', 'given_name', 'name']);
      const claims = await signedClaims(signed, token);
      assertDisclosure(claims, ['individual_id', 'given_name']);
      assert.equal(claims.individual_id, process.env.ESIGNET_DEMO_REFERENCE || '44a5ef0a-aaa2-574e-8969-1069bf62b948');
      subject = claims.sub;
      await assert.rejects(() => oidc.authorizationCodeGrant(signed.config, callback, {
        expectedState: first.pending.state, expectedNonce: first.pending.nonce,
        pkceCodeVerifier: first.pending.verifier, idTokenExpected: true
      }), (error) => error instanceof oidc.ResponseBodyError && error.error === 'invalid_grant');
    } finally { await first.close(); }
    console.log('esignet-protocol-proof: signed-userinfo-optional-denial PASS');

    stage = 'fresh-consent-no-expansion';
    const repeat = await beginLogin(browser, signed, requested, callbacks);
    try {
      await authenticate(repeat);
      const { token } = await finishLogin(repeat, signed, ['individual_id', 'gender', 'name']);
      assertDisclosure(await signedClaims(signed, token), ['individual_id', 'gender'], subject);
    } finally { await repeat.close(); }
    console.log('esignet-protocol-proof: fresh-consent-no-expansion PASS');

    stage = 'empty-selection';
    const empty = await beginLogin(browser, signed, { individual_id: null, given_name: null, name: null, gender: null }, callbacks);
    try {
      await authenticate(empty);
      const { token } = await finishLogin(empty, signed, []);
      assertDisclosure(await signedClaims(signed, token), [], subject);
    } finally { await empty.close(); }
    console.log('esignet-protocol-proof: empty-selection PASS');

    stage = 'encrypted-userinfo';
    const encryptedFlow = await beginLogin(browser, encrypted, requested, callbacks);
    try {
      await authenticate(encryptedFlow);
      const { token } = await finishLogin(encryptedFlow, encrypted, ['individual_id', 'given_name', 'name']);
      const claims = await encryptedClaims(encrypted, token);
      assertDisclosure(claims, ['individual_id', 'given_name']);
      assert.equal(claims.individual_id, process.env.ESIGNET_DEMO_REFERENCE || '44a5ef0a-aaa2-574e-8969-1069bf62b948');
      const repeatClaims = await encryptedClaims(encrypted, token);
      assertDisclosure(repeatClaims, ['individual_id', 'given_name'], claims.sub);
    } finally { await encryptedFlow.close(); }
    console.log('esignet-protocol-proof: encrypted-userinfo PASS');

    await writeFile(resultPath, JSON.stringify({ status: 'PASS', checks: 8, completedAt: new Date().toISOString() }), { mode: 0o600 });
  } catch (error) {
    // Diagnostic metadata is private and excludes messages, actual/expected
    // assertion values, browser URLs, claims, tokens, and key material.
    const sourceLine = error.stack?.match(/esignet-protocol-proof\.mjs:(\d+):/)?.[1];
    await writeFile(resultPath, JSON.stringify({
      status: 'FAIL', stage, errorName: error.name, errorCode: error.code,
      oauthError: error instanceof oidc.ResponseBodyError ? error.error : undefined,
      httpStatus: error instanceof oidc.ResponseBodyError ? error.status : undefined,
      grantFailure: grantFailureDescriptions.has(error.error_description) ? error.error_description : undefined,
      sourceLine, flowTrace: proofTrace
    }), { mode: 0o600 });
    console.error(`esignet-protocol-proof: ${stage} FAIL`);
    process.exitCode = 1;
  } finally {
    await browser?.close();
    server.closeAllConnections();
    await new Promise((resolveClose) => server.close(resolveClose));
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try { await main(); } catch {
    console.error('esignet-protocol-proof: startup FAIL');
    process.exitCode = 1;
  }
}
