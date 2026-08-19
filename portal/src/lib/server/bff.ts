// BFF glue: turn a MockEvaluation into a REDACTED ProofTrace and a RailEvent, and
// tee them to the reactive feeds. Server-only (redaction lives here); imported by
// the /api/evaluate route and the SSE stream, never into a client bundle.

import type { MockEvaluation } from '$lib/providers/mock';
import type { ProofTrace, RailChannel, RailEvent } from '$lib/types';
import { proofFeed, railFeed } from '$lib/providers/feeds.svelte';
import { scrubString } from './redact';

let traceSeq = 0;

// Build a redacted ProofTrace from a full MockEvaluation. The depth-1 human copy
// is allowlist-safe by construction (it never embeds a raw identifier; the mock
// authors it). depth-2 bodies are run through the redactor. depth-3 crypto carries
// no raw identifier, internal event id, or cryptographic bytes.
export function buildRedactedTrace(
  ev: MockEvaluation,
  opts?: { fieldId?: string }
): ProofTrace {
  const seq = ++traceSeq;
  const trace: ProofTrace = {
    id: ev.result.traceId,
    seq,
    ...(opts?.fieldId ? { fieldId: opts.fieldId } : {}),
    authority: ev.proof.authority,
    // depth 1: scrub defensively even though the mock authors these clean.
    headline: scrubString(ev.proof.headline),
    answered: scrubString(ev.proof.answered),
    notDisclosed: scrubString(ev.proof.notDisclosed),
    status: ev.proof.status,
    ts: new Date().toISOString(),
    purpose: ev.proof.purpose,
    resultState: ev.result.state,
    presentations: ev.proof.presentations,
    responseStatus: ev.raw.response.status,
    proof: ev.proof.crypto
  };
  return trace;
}

// Rail behavior is derived from the stable result state, never from a request
// body or upstream transport detail.
export function railFromStatus(ev: MockEvaluation): { channel: RailChannel; phase: RailEvent['phase'] } {
  switch (ev.result.state) {
    case 'fetched':
    case 'stale':
      return { channel: 'fetch', phase: 'sealed' };
    case 'verified':
    case 'false':
    case 'recovered':
      return { channel: 'verify', phase: 'sealed' };
    case 'error':
    case 'ambiguous':
      return { channel: 'denied', phase: 'denied' };
    case 'in_flight':
    case 'slow':
      return { channel: 'verify', phase: 'request' };
    case 'idle':
    case 'prefilled':
      return { channel: 'verify', phase: 'sealed' };
  }
}

export function buildRailEvent(ev: MockEvaluation): RailEvent | null {
  if (!ev.proof.authority) return null;
  const { channel, phase } = railFromStatus(ev);
  return {
    id: `${ev.result.traceId}:${phase}`,
    authority: ev.proof.authority,
    channel,
    phase,
    ts: new Date().toISOString()
  };
}

// Tee a redacted trace + rail event to the feeds. Returns the trace so the route
// can also serialize it for the SSE stream.
export function teeToFeeds(
  ev: MockEvaluation,
  opts: { sessionId: string; fieldId?: string }
): ProofTrace {
  const trace = buildRedactedTrace(ev, opts);
  proofFeed.pushTrace(opts.sessionId, trace);
  const railEvent = buildRailEvent(ev);
  if (railEvent) railFeed.pushRailEvent(railEvent);
  return trace;
}

// SSE serialization: a single `event: trace\ndata: <json>\n\n` frame. The JSON is
// the already-redacted trace, so the wire bytes never carry raw identifiers.
export function serializeTraceEvent(trace: ProofTrace): string {
  // Final safety net: the trace is already redacted by buildRedactedTrace, but scrub
  // the serialized frame once more so a raw identifier or bearer can never reach the
  // wire even if a future change adds an un-redacted field. scrubString is a no-op on
  // already-clean input, so this is defense in depth, not a behavior change.
  const data = scrubString(JSON.stringify(trace));
  return `event: trace\ndata: ${data}\n\n`;
}

// SSE heartbeat as a real named event. It MUST be a named event (not a `: comment`):
// EventSource silently swallows comment lines, so a comment heartbeat never reaches
// the client and its stall watchdog would trip ~15s after the last trace even on a
// healthy feed. A `event: heartbeat` frame is delivered to the client's
// addEventListener('heartbeat', ...) handler, which refreshes the watchdog. The
// payload carries no identifier, only a timestamp.
export function heartbeatFrame(): string {
  return `event: heartbeat\ndata: ${Date.now()}\n\n`;
}

// Reset the trace counter (tests / "nothing shared yet" landing).
export function resetTraceSeq(): void {
  traceSeq = 0;
}
