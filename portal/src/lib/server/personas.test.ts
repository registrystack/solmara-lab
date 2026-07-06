import { describe, expect, it } from 'vitest';
import { KNOWN_PERSONAS, resolvePersona } from './personas';

describe('persona handoff resolution', () => {
  it('resolves a known persona UIN to its mock session', () => {
    const session = resolvePersona('2300010248');
    expect(session).toEqual({ subject: '2300010248', displayName: 'Mateo Santos' });
  });

  it('rejects a UIN that is not on the published roster', () => {
    expect(resolvePersona('9999999999')).toBeNull();
    expect(resolvePersona('')).toBeNull();
    expect(resolvePersona(null)).toBeNull();
    expect(resolvePersona(undefined)).toBeNull();
  });

  it('binds the subject from the roster, never trusting an arbitrary string', () => {
    for (const [uin, name] of Object.entries(KNOWN_PERSONAS)) {
      expect(resolvePersona(uin)).toEqual({ subject: uin, displayName: name });
    }
  });
});
