<script lang="ts">
  import type { ProofTrace } from '$lib/types';
  import { IDENTITY_TRACE_ID } from './canned-traces.js';

  type Props = {
    traces: ProofTrace[];
    activeTraceId?: string;
    connected?: boolean;
  };

  let { traces, activeTraceId, connected = true }: Props = $props();
  let expanded = $state<Record<string, boolean>>({});

  const identityTrace = $derived(traces.find((trace) => trace.id === IDENTITY_TRACE_ID));
  const inFlightTraces = $derived(traces.filter((trace) => trace.status === 'in_flight'));
  const mainTraces = $derived(
    traces
      .filter((trace) => trace.id !== IDENTITY_TRACE_ID && trace.status !== 'in_flight')
      .slice()
      .sort((left, right) => right.seq - left.seq)
  );

  function statusLabel(trace: ProofTrace): string {
    switch (trace.status) {
      case 'in_flight': return 'In flight';
      case 'ok': return 'Verified';
      case 'false': return 'False (signed)';
      case 'denied': return 'Denied';
      case 'error': return 'Error';
    }
  }

  function authorityIcon(authority: string | undefined): string {
    switch (authority) {
      case 'civil': return '👤';
      case 'social': return '🏠';
      case 'agri': return '🌾';
      case 'certs': return '📜';
      case 'childCivil': return '📋';
      case 'population': return '🪪';
      case 'socialRegistry': return '🏠';
      case 'programme': return '🗂️';
      default: return '◧';
    }
  }

  function formatTs(ts: string): string {
    const parsed = new Date(ts);
    return Number.isNaN(parsed.valueOf())
      ? ts
      : parsed.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  }
</script>

<aside class="proof-inspector" aria-label="Proof Inspector">
  <header class="inspector-header">
    <span aria-hidden="true">◧</span>
    <span>PROOF INSPECTOR</span>
    {#if !connected}
      <span class="reconnect-pill" role="status">Reconnecting to proof feed</span>
    {/if}
  </header>

  <div class="entries-list">
    {#each inFlightTraces as trace (trace.id)}
      <article class="entry in-flight" aria-label="Request in flight: {trace.headline}">
        <div class="entry-top">
          <span aria-hidden="true">{authorityIcon(trace.authority)}</span>
          <strong>{trace.id}</strong>
          <span class="status">In flight</span>
          <time datetime={trace.ts}>{formatTs(trace.ts)}</time>
        </div>
        <p>{trace.headline}</p>
        <p><strong>Not disclosed:</strong> {trace.notDisclosed}</p>
      </article>
    {/each}

    {#each mainTraces as trace (trace.id)}
      <article class:active={trace.id === activeTraceId} class="entry {trace.status}" id="proof-{trace.id}">
        <div class="entry-top">
          <span aria-hidden="true">{authorityIcon(trace.authority)}</span>
          <strong>{trace.id}</strong>
          <span class="status">{statusLabel(trace)}</span>
          <time datetime={trace.ts}>{formatTs(trace.ts)}</time>
        </div>
        <p class="headline">{trace.headline}</p>
        <p>{trace.answered}</p>
        <p class="not-disclosed"><strong>Not disclosed:</strong> {trace.notDisclosed}</p>
        {#if trace.fieldId}<p class="field-ref">↳ for field “{trace.fieldId}”</p>{/if}

        <button
          class="expand-btn"
          type="button"
          aria-expanded={expanded[trace.id] ?? false}
          onclick={() => (expanded[trace.id] = !(expanded[trace.id] ?? false))}
        >
          {(expanded[trace.id] ?? false) ? '▾' : '▸'} Authority evidence
        </button>

        {#if expanded[trace.id] ?? false}
          <section class="details" aria-label="Safe authority evidence details">
            {#if trace.purpose}<p><strong>Purpose:</strong> <code>{trace.purpose}</code></p>{/if}
            {#if trace.responseStatus}<p><strong>Result status:</strong> {trace.responseStatus}</p>{/if}
            <p><strong>Stable result state:</strong> {trace.resultState}</p>
            {#if trace.presentations.length === 0}
              <p>No authority Evidence service was called.</p>
            {:else}
              <ul class="presentations">
                {#each trace.presentations as presentation}
                  <li>
                    <strong>{presentation.authority}</strong>
                    <span>Issuer: <code>{presentation.issuer}</code></span>
                    <span>Evidence service: <code>{presentation.serviceId}</code></span>
                    <span>Source: <strong>{presentation.source}</strong></span>
                  </li>
                {/each}
              </ul>
            {/if}
            {#if trace.proof}
              <dl class="proof-summary">
                <dt>Verified as</dt><dd>{trace.proof.credential}</dd>
                <dt>Issued by</dt><dd>{trace.proof.signedBy}</dd>
                <dt>Verification</dt><dd>{trace.proof.algorithm}</dd>
                <dt>Key discovery</dt><dd>{trace.proof.issuerKey}</dd>
                <dt>Bound to</dt><dd>{trace.proof.holderBound}</dd>
              </dl>
            {/if}
          </section>
        {/if}
      </article>
    {/each}

    {#if identityTrace}
      <article class="entry identity" id="proof-{identityTrace.id}">
        <div class="entry-top"><span aria-hidden="true">🪪</span><strong>{identityTrace.id}</strong><span class="status">Identity</span></div>
        <p class="headline">{identityTrace.headline}</p>
        <p>{identityTrace.answered}</p>
        <p class="not-disclosed"><strong>Not disclosed:</strong> {identityTrace.notDisclosed}</p>
      </article>
    {/if}

    {#if traces.length === 0}
      <p class="empty">No proof entries yet. Open a service to begin.</p>
    {/if}
  </div>
</aside>

<style>
  .proof-inspector { height: 100%; overflow: auto; background: var(--color-surface); border-left: 1px solid #d7dde6; }
  .inspector-header { position: sticky; top: 0; z-index: 1; display: flex; gap: var(--space-2); align-items: center; padding: var(--space-3); background: var(--color-chrome); color: white; font-family: var(--font-mono); font-weight: 700; }
  .reconnect-pill { margin-left: auto; font-size: var(--text-sm); color: var(--color-channel-amber); }
  .entries-list { display: grid; gap: var(--space-3); padding: var(--space-3); }
  .entry { border: 1px solid #d7dde6; border-left: 4px solid var(--color-channel-self); border-radius: var(--radius-md); padding: var(--space-3); background: var(--color-surface-raised); }
  .entry.ok { border-left-color: var(--color-channel-verify); }
  .entry.false { border-left-color: var(--color-channel-amber); }
  .entry.denied, .entry.error { border-left-color: var(--color-channel-denied); }
  .entry.active { outline: 2px solid var(--color-channel-fetch); outline-offset: 2px; }
  .entry-top { display: flex; align-items: center; gap: var(--space-2); font-family: var(--font-mono); font-size: var(--text-sm); }
  .entry-top time { margin-left: auto; }
  .status { border: 1px solid currentColor; border-radius: 999px; padding: 0 var(--space-2); }
  .headline { font-weight: 700; }
  .not-disclosed { color: #526174; }
  .field-ref { font-size: var(--text-sm); color: #526174; }
  .expand-btn { width: 100%; text-align: left; border: 0; border-top: 1px solid #d7dde6; background: transparent; padding: var(--space-2) 0 0; font: inherit; font-weight: 700; cursor: pointer; }
  .details { margin-top: var(--space-3); padding: var(--space-3); background: var(--color-surface); border-radius: var(--radius-sm); overflow-wrap: anywhere; }
  .details code { font-family: var(--font-mono); font-size: var(--text-sm); }
  .presentations { display: grid; gap: var(--space-3); padding-left: var(--space-4); }
  .presentations li { display: grid; gap: var(--space-1); }
  .proof-summary { display: grid; grid-template-columns: minmax(7rem, auto) 1fr; gap: var(--space-1) var(--space-3); margin-bottom: 0; }
  .proof-summary dt { font-weight: 700; }
  .proof-summary dd { margin: 0; }
  .empty { text-align: center; color: #526174; padding: var(--space-6); }
</style>
