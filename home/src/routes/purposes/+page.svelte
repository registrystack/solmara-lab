<script lang="ts">
  import type { PurposeView } from '$lib/types';
  import CopyButton from '$lib/components/CopyButton.svelte';

  export let data: { purposes: PurposeView[] };
  $: purposes = data.purposes;
</script>

<svelte:head>
  <title>Purpose register · Solmara Visitor's Center</title>
  <meta name="description" content="The Solmara purpose register in plain language: what each purpose permits, who advertises it, and who enforces it." />
</svelte:head>

<main class="page-band reference-page">
  <div class="content">
    <p class="eyebrow">Purpose register</p>
    <h1>Every purpose in plain language</h1>
    <p class="lede">
      A purpose is the single reason a request is allowed to read evidence. Solmara publishes its
      purposes so anyone can check what each one permits. Every purpose link elsewhere on the site
      lands here. This page is rendered from the purpose catalogue, not written by hand.
    </p>

    <nav class="anchor-nav" aria-label="Purposes on this page">
      {#each purposes as purpose}
        <a href={`#${purpose.slug}`}>{purpose.story}</a>
      {/each}
    </nav>

    <div class="reference-list">
      {#each purposes as purpose}
        <article class="reference-card" id={purpose.slug}>
          <div class="reference-head">
            <div>
              <p class="eyebrow">{purpose.slug}</p>
              <h2>{purpose.story}</h2>
            </div>
            <a class="anchor-hash" href={`#${purpose.slug}`} aria-label="Link to this purpose">#</a>
          </div>

          {#if purpose.plainLanguage}
            <p class="plain">{purpose.plainLanguage}</p>
          {/if}

          <div class="iri-row">
            <code>{purpose.iri}</code>
            <CopyButton text={purpose.iri} label="Copy IRI" />
          </div>

          <dl class="meta-grid">
            <div>
              <dt>Advertised by</dt>
              <dd>{purpose.advertisedBy}</dd>
            </div>
            <div>
              <dt>Enforced by</dt>
              <dd><code>{purpose.enforcedBy}</code></dd>
            </div>
          </dl>

          {#if purpose.denialCodes.length}
            <div class="chip-row">
              <span class="chip-label">Denials:</span>
              {#each purpose.denialCodes as code}
                <a class="chip denial" href={`/problem-codes#${code}`}>{code}</a>
              {/each}
            </div>
          {/if}

          {#if purpose.storyLinks.length}
            <div class="chip-row">
              <span class="chip-label">Shown in:</span>
              {#each purpose.storyLinks as link}
                <a class="chip" href={`/stories/${link.storyId}#${link.stepId}`}>{link.storyTitle}: {link.stepLabel}</a>
              {/each}
            </div>
          {/if}
        </article>
      {/each}
    </div>

    <p class="back"><a href="/">Back to the Visitor's Center</a></p>
  </div>
</main>
