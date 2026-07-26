<script lang="ts">
  import type { Purpose, Scenario, StepRunEnvelope, StepRunResult } from '$lib/types';
  import { toCurl } from '$lib/curl';
  import { claimResults, hopsFromResult, isDenial, problemCode } from '$lib/runresult';
  import CopyButton from './CopyButton.svelte';

  export let scenarios: Scenario[] = [];
  export let purposes: Purpose[] = [];

  const minimumJourneyDuration = 1_200;
  const evidenceQuestions = [
    'Is Mateo’s birth registered?',
    'Is his population record active?',
    'Is he under five?',
    "Does his household meet the benefit's income rule?",
    'Is he not already enrolled for this benefit?'
  ];
  const evidenceLabels: Record<string, string> = {
    'birth-is-registered': 'Birth registration confirmed',
    'population-record-active': 'Population registration is active',
    'child-age-under-5': 'Age is under five',
    'household-below-poverty-threshold': "Household meets the benefit's income rule",
    'not-already-enrolled': 'No existing child-benefit enrolment'
  };

  let firstResult: StepRunResult | null = null;
  let flipResult: StepRunResult | null = null;
  let running = false;
  let reasking = false;
  let runFailed = false;
  let selectedPurpose = '';

  $: defaultScenario = scenarios.find((scenario) => scenario.id === 'birth-to-child-benefit') ?? scenarios[0];
  $: permittedPurpose = defaultScenario?.requester.purpose ?? '';
  $: wrongPurpose =
    purposes.find((purpose) => purpose.slug === 'pension-payment-review')?.iri ??
    purposes.find((purpose) => purpose.iri !== permittedPurpose)?.iri ??
    '';
  $: if (!selectedPurpose && wrongPurpose) selectedPurpose = wrongPurpose;
  $: selectedPurposeView = purposes.find((purpose) => purpose.iri === selectedPurpose);
  $: positivePreview = defaultScenario?.steps.find((step) => step.id === 'positive')?.request_preview;

  $: trace = hopsFromResult(firstResult);
  $: authorities = trace.map((hop) => hop.split(':')[0]).filter((authority, index, list) => list.indexOf(authority) === index);
  $: disclosed = claimResults(firstResult).filter((claim) => claim.satisfied !== false);
  $: flipCode = flipResult ? problemCode(flipResult) : null;
  $: flipDenied = isDenial(flipResult);
  $: journeyStatus = running
    ? 'Checking the four government offices.'
    : firstResult
      ? 'The five answers have returned. Mateo’s records stayed with the offices that hold them.'
      : 'Ready to run the check without sharing records.';

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
    runFailed = false;
    firstResult = null;
    flipResult = null;
    const resultPromise = runStep('positive', {});
    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (!prefersReducedMotion) {
      await Promise.all([
        resultPromise,
        new Promise((resolve) => window.setTimeout(resolve, minimumJourneyDuration))
      ]);
    }
    firstResult = await resultPromise;
    runFailed = firstResult === null;
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
      <p class="eyebrow">No. 02 · Run the live example</p>
      <h2>Can the child-benefit team check Mateo's application without collecting his personal records?</h2>
      <p>
        Mateo applies for child benefit. The team needs five yes-or-no answers held by four
        government offices. Each office checks its own records and returns only the permitted answer.
      </p>
    </div>

    <ol
      class:journey-running={running}
      class:journey-complete={Boolean(firstResult)}
      class="journey-steps"
      aria-label="What happens during the live check"
    >
      <li style="--journey-index: 0">
        <span class="journey-number">1</span>
        <div><strong>Mateo applies</strong><small>The child-benefit team begins its review.</small></div>
      </li>
      <li style="--journey-index: 1">
        <span class="journey-number">2</span>
        <div><strong>Five questions are sent</strong><small>Only the answers needed for this application.</small></div>
      </li>
      <li style="--journey-index: 2">
        <span class="journey-number">3</span>
        <div><strong>Four offices check</strong><small>Each office checks the records it already holds.</small></div>
      </li>
      <li style="--journey-index: 3">
        <span class="journey-number">4</span>
        <div><strong>Only answers return</strong><small>Mateo's underlying records stay where they are.</small></div>
      </li>
    </ol>
    <p class="visually-hidden" aria-live="polite">{journeyStatus}</p>

    <div class="lens">
      <div class="lens-request">
        <p class="eyebrow">Before the check</p>
        <h3>What the child-benefit team needs to know</h3>
        <ul class="question-list">
          {#each evidenceQuestions as question}
            <li>{question}</li>
          {/each}
        </ul>
        <p class="privacy-note">
          The team does not ask for registry rows, addresses, or Mateo's complete personal record.
        </p>
        <button class="primary" on:click={ask} disabled={running || !defaultScenario}>
          {running
            ? 'Checking four government offices…'
            : firstResult
              ? 'Run the check without sharing records again'
              : 'Run the check without sharing records'}
        </button>
        <p class="quiet-caption">This makes a real request to the running Solmara services.</p>
        {#if !defaultScenario}
          <p class="empty">The scenario runner is unavailable. The live example will return when the service is healthy.</p>
        {/if}
      </div>

      <div class="lens-result" aria-busy={running}>
        {#if !firstResult}
          <div class="result-placeholder">
            <p class="eyebrow">What comes back</p>
            <h3>{running ? 'The four offices are checking…' : 'Run the check to see what travels'}</h3>
            <p>
              {running
                ? 'Each office is checking its own records and preparing only a yes-or-no answer.'
                : 'The result will show the answers the team receives and the personal information that stays private.'}
            </p>
            {#if runFailed}
              <p class="empty">The live check did not complete. Try again when the scenario runner is healthy.</p>
            {/if}
          </div>
        {:else}
          <div class="result-content result-reveal">
            <p class="eyebrow">What came back</p>
            <div class="answer result-lead">
              <h3>{disclosed.length} answers received. Mateo's records stayed where they were.</h3>
              <p>
                The child-benefit team now has the five answers it needs to continue. The team,
                not Registry Stack, remains responsible for the final decision.
              </p>
            </div>
            <div class="disclosure-grid">
              <div>
                <h4>Answers received</h4>
                <ul class="answer-list">
                  {#each disclosed as claim}
                    <li><span aria-hidden="true">✓</span>{evidenceLabels[claim.id] ?? claim.id}</li>
                  {/each}
                </ul>
              </div>
              <div>
                <h4>What stayed private</h4>
                <p>Registry rows, addresses, income values, and every fact outside this review stayed with the offices that hold them.</p>
              </div>
            </div>
            <p class="authority-summary">
              <strong>{authorities.length || 4} government offices</strong> checked their own records.
              No central copy was created.
            </p>
            <details class="drawer technical-trace">
              <summary>See how this works technically</summary>
              <div class="technical-trace-content">
                <p><strong>Offices consulted:</strong> {authorities.join(', ')}</p>
                <h4>Machine-readable answers</h4>
                <ul class="claim-list">
                  {#each disclosed as claim}
                    <li><code>{claim.id}</code></li>
                  {/each}
                </ul>
                <h4>Request trace</h4>
                <ol class="trace">
                  {#each trace as hop}
                    <li>{hop}</li>
                  {/each}
                </ol>
              </div>
            </details>
          </div>
        {/if}
      </div>
    </div>

    {#if firstResult}
      <div class="boundary-challenge boundary-reveal" id="purpose-limitation">
        <div>
          <p class="eyebrow">Now test the safeguard</p>
          <h3>Can these answers be reused for something else?</h3>
          <p>
            No. This request is allowed only for Mateo's child-benefit review. Try to reuse it for
            a pension review and the same services must refuse.
          </p>
          <button class="primary" on:click={tryWrongPurpose} disabled={reasking || !wrongPurpose}>
            {reasking ? 'Testing the safeguard…' : 'Test the safeguard'}
          </button>
        </div>

        <div class="boundary-result" aria-live="polite">
          {#if !flipResult}
            <p class="lens-placeholder">
              Run the test to see whether a child-benefit request can be reused for a pension review.
            </p>
          {:else if flipDenied}
            <div class="boundary-answer result-reveal">
              <p class="eyebrow">Safeguard worked</p>
              <h4>The request was refused.</h4>
              <p>The answers approved for Mateo's child-benefit review cannot be requested for a pension review.</p>
              <details class="boundary-code">
                <summary>See the technical refusal code</summary>
                <p class="problem">
                  Stable problem code:
                  <a href={`/problem-codes#${flipCode}`}><code>{flipCode}</code></a>
                </p>
              </details>
            </div>
          {:else}
            <div class="answer">
              <h4>Evidence returned</h4>
              <p>That purpose is permitted for this request, so the services answered.</p>
            </div>
          {/if}
        </div>

        <details class="advanced-request">
          <summary>Explore other purposes or inspect the technical request</summary>
          <div class="advanced-request-grid">
            <div class="purpose-picker">
              <label for="alternate-purpose">
                Alternate purpose
                <select id="alternate-purpose" bind:value={selectedPurpose}>
                  {#each purposes as purpose}
                    <option value={purpose.iri}>{purpose.story}</option>
                  {/each}
                </select>
              </label>
              <p class="field-help">
                The request will carry <code>{selectedPurposeView?.slug ?? 'no-purpose-selected'}</code>.
              </p>
              <button class="secondary-action" on:click={() => askUnderPurpose(selectedPurpose)} disabled={reasking || !positivePreview}>
                Test this purpose
              </button>
            </div>
            <details class="request-inspector">
              <summary>View the request preview and curl</summary>
              <pre>{flipPreviewLine}</pre>
              {#if flipCurl}
                <CopyButton text={flipCurl} label="Copy as curl" />
              {/if}
            </details>
          </div>
        </details>
      </div>
    {/if}
  </div>
</section>
