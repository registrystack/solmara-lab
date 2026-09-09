import assert from 'node:assert/strict';
import { test } from 'node:test';
import { assertDisclosure, validateCallback, registration } from './esignet-protocol-proof.mjs';

test('disclosure proof catches extra cached attributes and changed subjects', () => {
  const released = { sub: 'pairwise', name: 'Synthetic citizen', iss: 'https://issuer.test', aud: 'client', exp: 200 };
  assert.doesNotThrow(() => assertDisclosure(released, ['name'], 'pairwise'));
  assert.throws(() => assertDisclosure({ ...released, gender: 'extra' }, ['name'], 'pairwise'));
  assert.throws(() => assertDisclosure({ ...released, sub: 'another' }, ['name'], 'pairwise'));
  assert.throws(() => assertDisclosure({ ...released, name: null }, ['name'], 'pairwise'));
  assert.doesNotThrow(() => assertDisclosure({ sub: 'pairwise', iat: 100 }, [], 'pairwise'));
  assert.throws(() => assertDisclosure(released, [], 'pairwise'));
});

test('callback proof rejects state confusion and code/error ambiguity', () => {
  const pending = { redirectUri: 'http://127.0.0.1:4315/callback', state: 'expected' };
  assert.doesNotThrow(() => validateCallback(new URL(`${pending.redirectUri}?state=expected&code=one`), pending));
  assert.doesNotThrow(() => validateCallback(new URL(`${pending.redirectUri}?state=expected&error=access_denied`), pending));
  for (const query of ['state=wrong&code=one', 'state=expected&state=expected&code=one',
    'state=expected&code=one&code=two', 'state=expected&error=access_denied&code=one', 'state=expected']) {
    assert.throws(() => validateCallback(new URL(`${pending.redirectUri}?${query}`), pending));
  }
  assert.throws(() => validateCallback(new URL('http://127.0.0.1:4316/callback?state=expected&code=one'), pending));
});

test('separate clients register JWS or JWE with only public verification and recipient keys', () => {
  const sig = { kty: 'RSA', use: 'sig', alg: 'RS256', n: 'public-modulus', e: 'AQAB' };
  const enc = { kty: 'RSA', use: 'enc', alg: 'RSA-OAEP-256', n: 'different-public-modulus', e: 'AQAB' };
  const signed = registration('signed', sig, undefined, 'http://127.0.0.1:4315/callback');
  const encrypted = registration('encrypted', sig, enc, 'http://127.0.0.1:4315/callback');
  assert.equal(signed.additionalConfig.userinfo_response_type, 'JWS');
  assert.equal(signed.encPublicKey, undefined);
  assert.equal(encrypted.additionalConfig.userinfo_response_type, 'JWE');
  assert.deepEqual(encrypted.encPublicKey, enc);
  assert.deepEqual(encrypted.clientAuthMethods, ['private_key_jwt']);
  assert.deepEqual(encrypted.authContextRefs, ['mosip:idp:acr:static-code']);
  assert.equal(encrypted.additionalConfig.pkce_required, true);
});
