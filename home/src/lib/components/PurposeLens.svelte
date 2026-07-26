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
  $: wrongPurpose =
    purposes.find((purpose) => purpose.slug === 'pension-payment-review')?.iri ??
    purposes.find((purpose) => purpose.iri !== permittedPurpose)?.iri ??
    '';
  $: if (!selectedPurpose && wrongPurpose) selectedPurpose = wrongPurpose;
  $: positivePreview = defaultScenario?.steps.find((step) => step.id === 'positive')?.request_preview;

  $: trace = hopsFromResult(firstResult);
  $: authorities = trace.map((hop) => hop.split(':')[0]).filter((authority, index, list) => list.indexOf(authority) === index);
  $: disclosed = claimResults(firstResult).filter((claim) => claim.satisfied !== false);
  $: flipCode = flipResult ? problemCode(flipResult) : null;
  $: flipDenied = isDenial(flipResult);

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

  async function askUnderPurpose(purpose: string) {
    if (!purpose) return;
    reasking = true;
    flipResult = null;
    flipResult = await runStep('positive', { purpose });
    reasking = false;
  }

  async function tryWrongPurpose() {
    selectedPurpose = wrongPurpose;
    await askUnderPurpose(wrongPurpose);
  }
</script>

<section class="page-band live-demo" id="purpose-lens">
  <div class="content">
    <div class="section-intro live-demo-intro">
      <p class="eyebrow">Run the live example</p>
      <h2>Can Mateo's child-benefit application be reviewed without copying his records?</h2>
      <p>
        A programme needs five bounded facts from four authorities. Run the real request, then try
        to reuse it for the wrong purpose.
      </p>
    </div>

    <div class="lens" aria-live="polite">
      <div class="lens-request">
        <p class="eyebrow">The request</p>
        <dl class="request-facts">
          <div><dt>Requester</dt><dd>Child-benefit programme</dd></div>
          <div><dt>Purpose</dt><dd>Child-benefit review</dd></div>
          <div><dt>Evidence needed</dt><dd>Five yes-or-no facts</dd></div>
          <div><dt>Held back</dt><dd>Source rows and unrelated personal details</dd></div>
        </dl>
        <button class="primary" on:click={ask} disabled={running || !defaultScenario}>
          {running ? 'Running live review' : firstResult ? 'Run the live review again' : 'Run the live review'}
        </button>
        <p class="quiet-caption">This calls the running Solmara services. The result is not canned.</p>
        {#if !defaultScenario}
          <p class="empty">The scenario runner is unavailable. The live example will return when the service is healthy.</p>
        {/if}
      </div>

      <div class="lens-result">
        {#if !firstResult}
          <div class="result-placeholder">
            <p class="eyebrow">The result</p>
            <h3>Evidence will arrive here</h3>
            <p>Source authorities keep their rows and return only the facts required for this review.</p>
          </div>
        {:else}
          <p class="eyebrow">The result</p>
          <div class="answer result-lead">
            <h3>{disclosed.length} required facts returned. No source records were shared.</h3>
            <p>
              The programme now has evidence for its review. Solmara Lab did not make the benefit decision.
            </p>
          </div>
          <div class="disclosure-grid">
            <div>
              <h4>Evidence returned</h4>
              <ul class="claim-list">
                {#each disclosed as claim}
                  <li><code>{claim.id}</code></li>
                {/each}
              </ul>
            </div>
            <div>
              <h4>Information held back</h4>
              <p>Registry rows, addresses, poverty scores, and every fact outside this review stayed at the source.</p>
            </div>
          </div>
          <p class="authority-summary"><strong>Authorities consulted:</strong> {authorities.join(', ')}</p>
          <details class="drawer technical-trace">
            <summary>Technical trace</summary>
            <ol class="trace">
              {#each trace as hop}
                <li>{hop}</li>
              {/each}
            </ol>
          </details>
        {/if}
      </div>
    </div>

    {#if firstResult}
      <div class="boundary-challenge" id="purpose-limitation">
        <div>
          <p class="eyebrow">Prove the boundary</p>
          <h3>Purpose is enforced, not just documented</h3>
          <p>
            Try to reuse the child-benefit request for pension review. The same services must refuse it.
          </p>
          <button class="primary" on:click={tryWrongPurpose} disabled={reasking || !wrongPurpose}>
            {reasking ? 'Trying the wrong purpose' : 'Try the wrong purpose'}
          </button>
        </div>

        <div class="boundary-result" aria-live="polite">
          {#if !flipResult}
            <p class="lens-placeholder">The enforced refusal will appear here.</p>
          {:else if flipDenied}
            <div class="boundary-answer">
              <p class="eyebrow">Boundary held</p>
              <h4>Request refused.</h4>
              <p>Child-benefit evidence cannot be requested for pension review.</p>
              <p class="problem">
                Stable problem code:
                <a href={`/problem-codes#${flipCode}`}><code>{flipCode}</code></a>
              </p>
            </div>
          {:else}
            <div class="answer">
              <h4>Evidence returned</h4>
              <p>That purpose is permitted for this request, so the services answered.</p>
            </div>
          {/if}
        </div>

        <details class="advanced-request">
          <summary>Choose another purpose or inspect the request</summary>
          <div class="advanced-request-grid">
            <div>
              <label>
                Purpose
                <select bind:value={selectedPurpose}>
                  {#each purposes as purpose}
                    <option value={purpose.iri}>{purpose.story} ({purpose.slug})</option>
                  {/each}
                </select>
              </label>
              <button on:click={() => askUnderPurpose(selectedPurpose)} disabled={reasking || !positivePreview}>
                Ask under the selected purpose
              </button>
            </div>
            <div>
              <pre>{flipPreviewLine}</pre>
              {#if flipCurl}
                <CopyButton text={flipCurl} label="Copy as curl" />
              {/if}
            </div>
          </div>
        </details>
      </div>
    {/if}
  </div>
</section>
