import { describe, expect, it } from 'vitest';
import {
  containsRawIdentifier,
  pickAllowedMeta,
  redactBody,
  redactRequest,
  redactResponse,
  scrubString
} from './redact';

describe('portal proof redaction boundary', () => {
  it('scrubs identifiers, credentials, private keys, and compact JWS values', () => {
    const dirty = [
      '2300010248',
      'CP-2001',
      'FR-1001',
      'Bearer secret-token-123',
      'x-api-key: secret-key-123',
      '-----BEGIN PRIVATE KEY-----\nsecret\n-----END PRIVATE KEY-----',
      `${'a'.repeat(20)}.${'b'.repeat(20)}.${'c'.repeat(20)}`
    ].join(' ');
    const clean = scrubString(dirty);

    expect(containsRawIdentifier(clean)).toBe(false);
    expect(clean).not.toMatch(/2300010248|CP-2001|FR-1001|secret-token|secret-key/);
    expect(clean).toContain('Bearer [redacted]');
    expect(clean).toContain('[private key redacted]');
    expect(clean).toContain('[JWS redacted]');
  });

  it('never projects request or response bodies', () => {
    const request = redactRequest({
      method: 'POST',
      url: 'https://cra-evidence.example/v1/evidence?uin=2300010248',
      body: { subjects: [{ selector: { values: { uin: '2300010248', farmer: 'FR-1001' } } }] }
    });
    const response = redactResponse({ status: 200, body: { protected: 'raw', payload: 'raw', signature: 'raw' } });

    expect(request).toEqual({ method: 'POST', url: 'https://cra-evidence.example/v1/evidence?uin=[redacted]' });
    expect(response).toEqual({ status: 200 });
    expect(redactBody({ selector: 'FR-1001' })).toEqual({});
    expect(JSON.stringify({ request, response })).not.toMatch(/subjects|selector|protected|payload|signature|FR-1001/);
  });

  it('allowlists only safe presentation metadata and scrubs string values', () => {
    expect(pickAllowedMeta({
      authority: 'Civil Registration Authority',
      issuer: 'did:web:id.registrystack.org:solmara:authority:cra',
      serviceId: 'cra-evidence',
      source: 'Relay lookup',
      selector: 'FR-1001',
      token: 'secret'
    })).toEqual({
      authority: 'Civil Registration Authority',
      issuer: 'did:web:id.registrystack.org:solmara:authority:cra',
      serviceId: 'cra-evidence',
      source: 'Relay lookup'
    });
  });
});
