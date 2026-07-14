<script lang="ts">
  import { onMount } from 'svelte';
  import type { RequestSource, Scenario, ScenarioStep, StepRunEnvelope, StepRunResult } from '$lib/types';
  import { toCurl } from '$lib/curl';
  import { claimResults, isDenial, problemCode, responseStatus } from '$lib/runresult';
  import CopyButton from '$lib/components/CopyButton.svelte';

  export let data: { scenario: Scenario };
  $: scenario = data.scenario;

  let results: Record<string, StepRunResult | null> = {};
  let runningStep = '';
  let runningAll = false;

  function isBoundary(step: ScenarioStep): boolean {
    return step.id.includes('control') || step.id.includes('denial');
  }

  function credentialResult(steps: Record<string, StepRunResult | null>, story: Scenario): StepRunResult | null {
    for (const step of story.steps) {
      const result = steps[step.id];
      if (result?.credential) return result;
    }
    return null;
  }

  function accountabilityResult(steps: Record<string, StepRunResult | null>, story: Scenario): StepRunResult | null {
    const positive = steps['positive'];
    if (positive && !isDenial(positive)) return positive;
    for (const step of story.steps) {
      const result = steps[step.id];
      if (result && !isDenial(result) && claimResults(result).length) return result;
    }
    return null;
  }

  $: credential = credentialResult(results, scenario);
  $: accountability = accountabilityResult(results, scenario);
  $: applicationEvidence = isCollectedApplicationEvidence(accountability) ? accountability : null;

  async function run(step: ScenarioStep): Promise<void> {
    runningStep = step.id;
    try {
      const response = await fetch(`/api/scenarios/${scenario.id}/steps/${step.id}/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({})
      });
      const envelope = (await response.json()) as StepRunEnvelope;
      results = { ...results, [step.id]: envelope.result ?? null };
      if (typeof history !== 'undefined') history.replaceState(null, '', `#${step.id}`);
    } catch {
      results = { ...results, [step.id]: null };
    } finally {
      runningStep = '';
    }
  }

  async function runAll(): Promise<void> {
    runningAll = true;
    for (const step of scenario.steps) {
      await run(step);
    }
    runningAll = false;
  }

  function requestBlock(result: StepRunResult): string {
    return sourceBlock(result.request_source);
  }

  function sourceBlock(source: RequestSource): string {
    const lines = [`${source.method} ${source.url}`];
    for (const [key, value] of Object.entries(source.headers ?? {})) lines.push(`${key}: ${value}`);
    if (source.body !== undefined && source.body !== null) {
      lines.push('', JSON.stringify(source.body, null, 2));
    }
    return lines.join('\n');
  }

  function credentialVct(result: StepRunResult | null): string | null {
    if (typeof result?.credential?.vct === 'string') {
      return result.credential.vct;
    }
    const body = result?.credential_response_source?.body;
    if (body && typeof body === 'object' && typeof (body as { vct?: unknown }).vct === 'string') {
      return (body as { vct: string }).vct;
    }
    return null;
  }

  function truncate(value: string | null | undefined, head = 24): string {
    if (!value) return '';
    return value.length > head * 2 ? `${value.slice(0, head)}…${value.slice(-8)}` : value;
  }

  function orchestrationField(result: StepRunResult, field: 'service_id' | 'decision'): string {
    const body = result.response_source.body;
    if (!body || typeof body !== 'object') return 'Not reported';
    const orchestration = (body as { orchestration?: unknown }).orchestration;
    if (!orchestration || typeof orchestration !== 'object') return 'Not reported';
    const value = (orchestration as Record<string, unknown>)[field];
    return typeof value === 'string' && value ? value : 'Not reported';
  }

  function isCollectedApplicationEvidence(result: StepRunResult | null): result is StepRunResult {
    if (!result?.source_trace?.length) return false;
    return orchestrationField(result, 'service_id') === 'child-benefit-federator';
  }

  function sourceAuthorityCount(result: StepRunResult): number {
    const serviceIds = (result.source_trace ?? [])
      .map((source) => source.service_id)
      .filter((serviceId): serviceId is string => typeof serviceId === 'string' && serviceId.length > 0);
    return new Set(serviceIds).size;
  }

  onMount(() => {
    const hash = window.location.hash.replace('#', '');
    if (hash) document.getElementById(hash)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
</script>

<svelte:head>
  <title>{scenario.title} · Solmara Visitor's Center</title>
  <meta name="description" content={scenario.proves} />
</svelte:head>

<main class="story">
  <section class="page-band story-intro">
    <div class="content">
      <p class="eyebrow">{scenario.domain}</p>
      <h1>{scenario.title}</h1>
      <p class="proves">{scenario.proves}</p>
      <div class="standards">
        <span>DCI CRVS-to-SP</span><span>PublicSchema</span><span>SD-JWT VC</span><span>CPSV-AP</span><span>ODRL</span>
      </div>
      <div class="intro-grid">
        <div class="actor-card">
          <p class="eyebrow">Your role</p>
          <p>You are the {scenario.actor}.</p>
        </div>
        <div class="subject-card">
          <p class="eyebrow">Subject</p>
          <strong>{scenario.subject.name}</strong>
          <code>{scenario.subject.identifier}</code>
        </div>
      </div>
      <p class="boundary-statement">
        This story never discloses raw register rows or any fact outside its purpose
        <code>{scenario.requester.purpose}</code>.
      </p>
      <div class="story-actions">
        <button class="primary" on:click={runAll} disabled={runningAll}>{runningAll ? 'Running all steps' : 'Run all steps'}</button>
        <a href="/#stories">Back to all stories</a>
      </div>
    </div>
  </section>

  <section class="page-band">
    <div class="content stepper">
      {#each scenario.steps as step, index}
        {@const result = results[step.id]}
        {@const boundary = isBoundary(step)}
        <article class="story-step" class:boundary id={step.id}>
          <div class="step-head">
            <span class="step-number">{index + 1}</span>
            <div>
              <div class="step-title-row">
                <h2>{step.label}</h2>
                {#if boundary}<span class="boundary-tag">Boundary</span>{/if}
                <a class="step-anchor" href={`#${step.id}`} aria-label="Link to this step">#</a>
              </div>
              <p class="step-prompt">{step.prompt}</p>
              <p class="request-summary"><code>{step.request_summary}</code></p>
            </div>
          </div>

          <button on:click={() => run(step)} disabled={runningStep === step.id}>
            {runningStep === step.id ? 'Running' : step.button}
          </button>

          {#if result}
            {@const denied = isDenial(result)}
            <div class="step-result" class:denied>
              <h3 class="result-title">{result.friendly?.title ?? 'Response received'}</h3>
              <p class="result-message">{result.friendly?.message ?? ''}</p>
              {#if denied}
                {@const code = problemCode(result)}
                <p class="problem">
                  Refused with stable problem code:
                  <a href={`/problem-codes#${code}`}><code>{code}</code></a>
                </p>
              {/if}
              <details class="drawer">
                <summary>Technical detail</summary>
                <div class="drawer-body">
                  <div class="drawer-block">
                    <div class="drawer-head">
                      <h4>Request (published lab token)</h4>
                      <CopyButton text={toCurl(result.request_source)} label="Copy as curl" />
                    </div>
                    <pre>{requestBlock(result)}</pre>
                  </div>
                  <div class="drawer-block">
                    <h4>Response (HTTP {responseStatus(result) ?? 'none'})</h4>
                    <pre>{JSON.stringify(result.response_source, null, 2)}</pre>
                  </div>
                  {#if result.source_trace?.length}
                    <div class="drawer-block">
                      <h4>Source authority evidence</h4>
                      <div class="peer-trace">
                        {#each result.source_trace as source}
                          <div class="peer-call">
                            <h5>
                              {source.authority ?? source.service_id ?? 'Source authority'}
                              <code>{source.claims?.join(', ') ?? source.claim_id ?? source.profile ?? 'evidence'}</code>
                            </h5>
                            {#if source.request_source}
                              <pre>{sourceBlock(source.request_source)}</pre>
                            {:else if source.request_summary}
                              <pre>{JSON.stringify(source.request_summary, null, 2)}</pre>
                            {/if}
                            {#if source.response_source}
                              <pre>{JSON.stringify(source.response_source, null, 2)}</pre>
                            {:else if source.response_summary}
                              <pre>{JSON.stringify(source.response_summary, null, 2)}</pre>
                            {/if}
                          </div>
                        {/each}
                      </div>
                    </div>
                  {/if}
                </div>
              </details>
            </div>
          {/if}
        </article>
      {/each}
    </div>
  </section>

  <section class="page-band credential-moment" id="credential">
    <div class="content">
      <p class="eyebrow">{applicationEvidence ? 'Application evidence' : 'Credential moment'}</p>
      <h2>{applicationEvidence ? 'The programme receives source-owned predicates' : 'The caseworker now holds a real credential'}</h2>
      {#if applicationEvidence}
        <div class="inspector">
          <p><span>Status</span><strong class="issued">Evidence returned</strong></p>
          <p><span>Collector</span>{orchestrationField(applicationEvidence, 'service_id')}</p>
          <p><span>Source authorities</span>{sourceAuthorityCount(applicationEvidence)}</p>
          <p><span>Decision</span>{orchestrationField(applicationEvidence, 'decision')}</p>
        </div>
        <div class="disclosure-grid">
          <div>
            <h4>Disclosed to the programme</h4>
            <ul class="claim-list">
              {#each claimResults(applicationEvidence) as claim}
                <li><code>{claim.id}</code> {claim.satisfied === true ? 'met' : claim.satisfied === false ? 'not met' : ''}</li>
              {/each}
            </ul>
          </div>
          <div>
            <h4>Held back</h4>
            <p>Raw register rows stay with each authority, and the programme keeps ownership of its final eligibility decision.</p>
          </div>
        </div>
      {:else if credential?.credential}
        {@const summary = credential.credential}
        {#if summary.status === 'issued'}
          {@const vct = credentialVct(credential)}
          <div class="inspector">
            <p><span>Status</span><strong class="issued">Issued</strong></p>
            <p><span>Profile</span>{summary.profile}</p>
            {#if vct}<p><span>vct</span><code>{vct}</code></p>{/if}
            <p><span>Format</span><code>{summary.format}</code></p>
            <p><span>Issuer</span>{summary.issuer ?? 'unknown'}</p>
            <p><span>Expires</span>{summary.expires_at ?? 'unknown'}</p>
            <p><span>Disclosures</span>{summary.disclosures ?? 0}</p>
            <p><span>Holder binding</span><code>{truncate(summary.holder_id)}</code></p>
            <p><span>Compact SD-JWT</span><code class="preview">{summary.compact_preview ?? ''}</code></p>
          </div>
          <div class="disclosure-grid">
            <div>
              <h4>Disclosed to the caseworker</h4>
              <ul class="claim-list">
                {#each claimResults(credential) as claim}
                  <li><code>{claim.id}</code></li>
                {/each}
              </ul>
            </div>
            <div>
              <h4>Withheld from the credential</h4>
              <p>Raw register rows and every field outside the purpose stay with the issuing authority.</p>
            </div>
          </div>
        {:else}
          <p class="not-issued">
            Not issued: <code>{summary.reason ?? 'unknown'}</code>
            {#if summary.message}<br /><span>{summary.message}</span>{/if}
          </p>
        {/if}
      {:else}
        <p class="inspector-empty">Run the evaluation above to inspect the resulting credential or application evidence.</p>
      {/if}
    </div>
  </section>

  <section class="page-band accountability" id="accountability">
    <div class="content">
      <p class="eyebrow">Accountability</p>
      <h2>{applicationEvidence ? 'What the source trace recorded about this access' : 'What the Notary recorded about this access'}</h2>
      {#if accountability}
        {@const first = claimResults(accountability)[0]?.raw ?? {}}
        <div class="provenance">
          {#each ['provenance', 'matching', 'target_ref'] as field}
            {#if first[field] !== undefined}
              <div class="provenance-block">
                <h4>{field}</h4>
                <pre>{JSON.stringify(first[field], null, 2)}</pre>
              </div>
            {/if}
          {/each}
          {#if first.provenance === undefined && first.matching === undefined && first.target_ref === undefined}
            <p>The evaluation returned claim results; per-claim provenance fields were not present in this response.</p>
          {/if}
        </div>
      {:else}
        <p class="inspector-empty">Run an evaluation step to see the proof trace.</p>
      {/if}
      <p class="audit-note">Reading the registry authority's own audit log is a product capability candidate, tracked separately.</p>
    </div>
  </section>
</main>
