<script lang="ts">
  import type { Purpose, Scenario, StepRunEnvelope, StepRunResult } from '$lib/types';
  import { toCurl } from '$lib/curl';
  import { claimResults, hopsFromResult, isDenial, problemCode } from '$lib/runresult';
  import CopyButton from './CopyButton.svelte';

  export let scenarios: Scenario[] = [];
  export let purposes: Purpose[] = [];

  let firstResult: StepRunResult | null = null;
  let flipResult: StepRunResult | null = null;
  let running = false;
  let reasking = false;
  let selectedPurpose = '';

  $: defaultScenario = scenarios.find((scenario) => scenario.id === 'birth-to-child-benefit') ?? scenarios[0];
  $: permittedPurpose = defaultScenario?.requester.purpose ?? '';
  $: if (!selectedPurpose && permittedPurpose) selectedPurpose = permittedPurpose;
  $: positivePreview = defaultScenario?.steps.find((step) => step.id === 'positive')?.request_preview;

  // Feel-before-name: only reveal product vocabulary once a run has completed.
  $: named = firstResult !== null;
  $: trace = hopsFromResult(firstResult);
  $: disclosed = claimResults(firstResult).filter((claim) => claim.satisfied !== false);
  $: flipCode = flipResult ? problemCode(flipResult) : null;
  $: flipDenied = isDenial(flipResult);

  // The pending flip request preview and curl update together as the selector changes.
  $: flipHeaders = (selectedPurpose ? { 'Data-Purpose': selectedPurpose } : {}) as Record<string, string>;
  $: flipPreviewLine = positivePreview
    ? `${positivePreview.method} ${positivePreview.url}\nData-Purpose: ${selectedPurpose}`
    : '';
  $: flipCurl = positivePreview ? toCurl(positivePreview, flipHeaders) : '';

  async function runStep(step: string, body: Record<string, unknown>): Promise<StepRunResult | null> {
    if (!defaultScenario) return null;
    try {
      const response = await fetch(`/api/scenarios/${defaultScenario.id}/steps/${step}/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      const envelope = (await response.json()) as StepRunEnvelope;
      return envelope.result ?? null;
    } catch {
      return null;
    }
  }

  async function ask() {
    running = true;
    firstResult = null;
    flipResult = null;
    firstResult = await runStep('positive', {});
    running = false;
  }

  async function reask() {
    reasking = true;
    flipResult = null;
    flipResult = await runStep('positive', { purpose: selectedPurpose });
    reasking = false;
  }
</script>

<section class="hero" id="purpose-lens">
  <div class="hero-copy">
    <h1>Republic of Solmara Visitor's Center</h1>
    <p class="subtitle">A live exhibit for how one government answers questions about its residents without handing over their records.</p>
    <div class="time-links" aria-label="Visit by available time">
      <a href="#purpose-lens">3 minutes: ask a question</a>
      <a href="#stories">15 minutes: one guided story</a>
      <a href="#engineer-door">1 hour: run the country yourself</a>
    </div>
  </div>

  <div class="lens" aria-live="polite">
    <div class="lens-request">
      <h2>Is Mateo Santos's birth registered, so his family can be reviewed for child benefit?</h2>
      <div class="actions">
        <button class="primary" on:click={ask} disabled={running || !defaultScenario}>
          {running ? 'Asking' : firstResult ? 'Ask again' : 'Ask'}
        </button>
      </div>
      <p class="quiet-caption">This will ask the government of Solmara, live. Nothing is canned.</p>
      {#if !defaultScenario}
        <p class="empty">Scenario runner is unavailable. The live ask will return when the service is healthy.</p>
      {/if}
    </div>

    <div class="lens-result">
      {#if !firstResult}
        <p class="lens-placeholder">The answer arrives here after you ask.</p>
      {:else}
        <ol class="trace">
          {#each trace as hop}
            <li>{hop}</li>
          {/each}
        </ol>
        <div class="answer">
          <h3>{firstResult.friendly?.title ?? 'Answer returned'}</h3>
          <p>{firstResult.friendly?.message ?? ''}</p>
        </div>
        <div class="disclosure-grid">
          <div>
            <h4>Disclosed</h4>
            {#if disclosed.length}
              <ul class="claim-list">
                {#each disclosed as claim}
                  <li><code>{claim.id}</code> {claim.satisfied === true ? 'met' : claim.satisfied === false ? 'not met' : ''}</li>
                {/each}
              </ul>
            {:else}
              <p>Only the yes-or-no answers the question needed.</p>
            {/if}
          </div>
          <div>
            <h4>Held back</h4>
            <p>Raw register rows, cause of death, poverty scores, and every fact outside this question stayed inside the government.</p>
          </div>
        </div>
      {/if}
    </div>
  </div>

  {#if named}
    <div class="content naming-moment" id="purpose-limitation">
      <p class="eyebrow">What you just saw</p>
      <h3>That is purpose limitation.</h3>
      <p>The government answered exactly the question you were allowed to ask, and nothing more. Now ask the same question under a different purpose and watch what happens.</p>

      <div class="flip">
        <div class="flip-request">
          <label>
            Purpose
            <select bind:value={selectedPurpose}>
              {#each purposes as purpose}
                <option value={purpose.iri}>{purpose.story} ({purpose.iri.split('/').pop()})</option>
              {/each}
            </select>
          </label>
          <div class="actions">
            <button on:click={reask} disabled={reasking || !positivePreview}>
              {reasking ? 'Asking' : 'Ask under this purpose'}
            </button>
          </div>
          <pre>{flipPreviewLine}</pre>
          {#if flipCurl}
            <div class="curl-row">
              <CopyButton text={flipCurl} label="Copy as curl" />
            </div>
          {/if}
        </div>

        <div class="flip-result">
          {#if !flipResult}
            <p class="lens-placeholder">Pick a purpose and ask. A wrong purpose gets a live refusal.</p>
          {:else if flipDenied}
            <div class="boundary-answer">
              <h4>{flipResult.friendly?.title ?? 'Request refused'}</h4>
              <p class="problem">
                Refused with stable problem code:
                <a href={`/problem-codes#${flipCode}`}><code>{flipCode}</code></a>
              </p>
            </div>
          {:else}
            <div class="answer">
              <h4>{flipResult.friendly?.title ?? 'Answer returned'}</h4>
              <p>That purpose is permitted here, so the government answered.</p>
            </div>
          {/if}
        </div>
      </div>
    </div>
  {/if}
</section>
