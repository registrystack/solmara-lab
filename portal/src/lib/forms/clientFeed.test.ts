import { describe, it, expect, beforeEach } from 'vitest';
import { clientFeed } from './clientFeed.svelte';
import type { ProofTrace } from '$lib/types';

// The watchdog logic is unit-tested directly (markAlive / tickWatchdog take an
// injected `now`) so we never need a live EventSource. This is the logic that the
// SSE heartbeat drives: a heartbeat keeps the feed "connected", and the watchdog
// only trips after the stall window with no heartbeat.
describe('ClientFeed watchdog', () => {
  beforeEach(() => clientFeed.reset());

  it('markAlive flags the feed connected', () => {
    clientFeed.markAlive(1000);
    expect(clientFeed.connected).toBe(true);
  });

  it('does not trip within the stall window after a heartbeat', () => {
    clientFeed.markAlive(1000);
    clientFeed.tickWatchdog(1000 + 14_000);
    expect(clientFeed.connected).toBe(true);
  });

  it('trips once the stall window passes with no heartbeat', () => {
    clientFeed.markAlive(1000);
    clientFeed.tickWatchdog(1000 + 16_000);
    expect(clientFeed.connected).toBe(false);
  });

  it('a later heartbeat recovers the connected flag after a stall', () => {
    clientFeed.markAlive(1000);
    clientFeed.tickWatchdog(1000 + 16_000);
    expect(clientFeed.connected).toBe(false);
    clientFeed.markAlive(20_000);
    expect(clientFeed.connected).toBe(true);
  });

  it('does not invent a Civil rail event for an application-owned trace', () => {
    const trace: ProofTrace = {
      id: 'event-application',
      seq: 1,
      headline: 'Portal decision from source predicates',
      answered: 'Portal application answered: eligible = true',
      notDisclosed: 'Not disclosed: source rows',
      status: 'ok',
      ts: '2026-07-15T00:00:00Z',
      request: {
        method: 'MULTI',
        url: 'solmara://citizen-portal/application-composition',
        body: { disclosure: 'decision' }
      }
    };

    clientFeed.applyTrace(trace);

    expect(clientFeed.traces).toHaveLength(1);
    expect(clientFeed.railEvents).toHaveLength(0);
  });
});
