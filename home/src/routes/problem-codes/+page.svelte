<script lang="ts">
  import type { ProblemCode } from '$lib/types';
  import CopyButton from '$lib/components/CopyButton.svelte';
  import ReferenceHero from '$lib/components/ReferenceHero.svelte';

  export let data: { codes: ProblemCode[] };
  $: codes = data.codes;
  $: facts = [
    { value: codes.length, label: 'stable problem codes' },
    { value: new Set(codes.map((code) => code.problemJson.status)).size, label: 'HTTP refusal statuses' },
    { value: 'RFC 9457', label: 'response format' }
  ];
</script>

<svelte:head>
  <title>Problem codes · Solmara Lab</title>
  <meta name="description" content="The stable problem codes the Solmara stack returns when it refuses a request, in plain language, with the story steps that demonstrate them." />
</svelte:head>

<main class="reference-surface reference-page">
  <ReferenceHero
    eyebrow="Problem codes"
    title="Make every refusal predictable"
    description="A refusal carries a stable machine-readable code, a human explanation, and an RFC 9457 response shape. Tooling can branch on the code while people can understand which trust boundary held."
    active="problem-codes"
    {facts}
  />

  <section class="page-band reference-body">
    <div class="content">
      <nav class="section-index" aria-label="Problem codes on this page">
        <span>Jump to a code</span>
        {#each codes as code}
          <a href={`#${code.code}`}>{code.code}</a>
        {/each}
      </nav>

      <div class="reference-list">
        {#each codes as code, index}
          <article class="reference-card problem-card" id={code.code}>
            <div class="reference-card-index" aria-hidden="true">{String(index + 1).padStart(2, '0')}</div>
            <div class="reference-card-content">
              <div class="reference-head">
                <div>
                  <p class="eyebrow">HTTP {code.problemJson.status} · {code.title}</p>
                  <h2><code>{code.code}</code></h2>
                </div>
                <a class="anchor-hash" href={`#${code.code}`} aria-label="Link to this code">#</a>
              </div>

              <p class="plain">{code.meaning}</p>

              <div class="iri-row">
                <span class="iri-label">Problem type</span>
                <code>{code.typeUri}</code>
                <CopyButton text={code.typeUri} label="Copy type URI" />
              </div>

              {#if code.purposeSlugs.length}
                <div class="chip-row">
                  <span class="chip-label">Referenced by</span>
                  {#each code.purposeSlugs as slug}
                    <a class="chip" href={`/purposes#${slug}`}>{slug}</a>
                  {/each}
                </div>
              {/if}

              {#if code.demonstratedBy.length}
                <div class="chip-row">
                  <span class="chip-label">Demonstrated in</span>
                  {#each code.demonstratedBy as link}
                    <a class="chip" href={`/stories/${link.storyId}#${link.stepId}`}>{link.storyTitle}: {link.stepLabel}</a>
                  {/each}
                </div>
              {:else if code.coverage}
                <p class="coverage">{code.coverage}</p>
              {/if}

              <details class="drawer response-shape">
                <summary>Inspect the problem+json response</summary>
                <pre>{JSON.stringify(code.problemJson, null, 2)}</pre>
              </details>
            </div>
          </article>
        {/each}
      </div>

      <p class="back"><a href="/developers">Back to the developer workspace</a></p>
    </div>
  </section>
</main>
