<script lang="ts">
  import type { ProblemCode } from '$lib/types';
  import CopyButton from '$lib/components/CopyButton.svelte';

  export let data: { codes: ProblemCode[] };
  $: codes = data.codes;
</script>

<svelte:head>
  <title>Problem codes · Solmara Visitor's Center</title>
  <meta name="description" content="The stable problem codes the Solmara stack returns when it refuses a request, in plain language, with the story steps that demonstrate them." />
</svelte:head>

<main class="page-band reference-page">
  <div class="content">
    <p class="eyebrow">Problem codes</p>
    <h1>When the stack says no, it says so the same way every time</h1>
    <p class="lede">
      A problem code is a stable machine-readable string in a refusal. It never changes wording, so
      tooling can rely on it. These codes are assembled from the purpose catalogue and the guided
      story metadata, not from prose that can drift. Each refusal is returned as problem+json
      (RFC 9457, the standard HTTP problem format).
    </p>

    <nav class="anchor-nav" aria-label="Problem codes on this page">
      {#each codes as code}
        <a href={`#${code.code}`}>{code.code}</a>
      {/each}
    </nav>

    <div class="reference-list">
      {#each codes as code}
        <article class="reference-card" id={code.code}>
          <div class="reference-head">
            <div>
              <h2><code>{code.code}</code></h2>
              <p class="attribution">{code.title} · HTTP {code.problemJson.status}</p>
            </div>
            <a class="anchor-hash" href={`#${code.code}`} aria-label="Link to this code">#</a>
          </div>

          <p class="plain">{code.meaning}</p>

          <div class="iri-row">
            <code>{code.typeUri}</code>
            <CopyButton text={code.typeUri} label="Copy type URI" />
          </div>

          {#if code.purposeSlugs.length}
            <div class="chip-row">
              <span class="chip-label">Referenced by:</span>
              {#each code.purposeSlugs as slug}
                <a class="chip" href={`/purposes#${slug}`}>{slug}</a>
              {/each}
            </div>
          {/if}

          {#if code.demonstratedBy.length}
            <div class="chip-row">
              <span class="chip-label">Demonstrated in:</span>
              {#each code.demonstratedBy as link}
                <a class="chip" href={`/stories/${link.storyId}#${link.stepId}`}>{link.storyTitle}: {link.stepLabel}</a>
              {/each}
            </div>
          {:else if code.coverage}
            <p class="coverage">{code.coverage}</p>
          {/if}

          <details class="drawer">
            <summary>problem+json shape</summary>
            <pre>{JSON.stringify(code.problemJson, null, 2)}</pre>
          </details>
        </article>
      {/each}
    </div>

    <p class="back"><a href="/">Back to the Visitor's Center</a></p>
  </div>
</main>
