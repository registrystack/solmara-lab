import { describe, it, expect } from 'vitest';
import { buildRailEvent, heartbeatFrame } from './bff';
import { MockEvidenceProvider, PERSONA } from '$lib/providers/mock';

describe('SSE heartbeat framing', () => {
  it('is a real named event, not an SSE comment (EventSource swallows comments)', () => {
    // Regression guard: the heartbeat used to be a `: comment`, which EventSource
    // silently drops. That meant the client watchdog never saw it and tripped the
    // reconnect pill ~15s after the last trace. A named `event: heartbeat` frame is
    // delivered to the client's addEventListener('heartbeat', ...) handler.
    const frame = heartbeatFrame();
    expect(frame.startsWith(':')).toBe(false);
    expect(frame).toMatch(/^event: heartbeat\n/);
    expect(frame).toMatch(/\ndata: /);
    expect(frame.endsWith('\n\n')).toBe(true);
  });

  it('does not assign an application-owned decision to an authority rail', async () => {
    const evaluation = await new MockEvidenceProvider().evaluateDetailed(
      { id: 'combined-support-eligibility', label: 'Eligibility', kind: 'decision' },
      { subject: PERSONA.rafael }
    );

    expect(evaluation.proof.authority).toBeUndefined();
    expect(buildRailEvent(evaluation)).toBeNull();
  });
});
