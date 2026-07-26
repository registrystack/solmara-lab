<script lang="ts">
  import type { PurposeView } from '$lib/types';
  import CopyButton from '$lib/components/CopyButton.svelte';
  import ReferenceHero from '$lib/components/ReferenceHero.svelte';

  export let data: { purposes: PurposeView[] };
  $: purposes = data.purposes;
  $: facts = [
    { value: purposes.length, label: 'published purposes' },
    { value: purposes.reduce((total, purpose) => total + purpose.storyLinks.length, 0), label: 'demonstrated steps' },
    { value: new Set(purposes.flatMap((purpose) => purpose.denialCodes)).size, label: 'stable denial codes' }
  ];
</script>

<svelte:head>
  <title>Purpose register · Solmara Lab</title>
  <meta name="description" content="The Solmara purpose register in plain language: what each purpose permits, who advertises it, and who enforces it." />
</svelte:head>

<main class="reference-surface reference-page">
  <ReferenceHero
    eyebrow="Purpose register"
    title="See exactly why evidence may be requested"
    description="A purpose is the single declared reason a request may read evidence. This live register explains what each purpose permits, who advertises it, who enforces it, and which refusal appears when the boundary is crossed."
    active="purposes"
    {facts}
  />

  <section class="page-band reference-body">
    <div class="content">
      <nav class="section-index" aria-label="Purposes on this page">
        <span>Jump to a purpose</span>
        {#each purposes as purpose}
          <a href={`#${purpose.slug}`}>{purpose.story}</a>
        {/each}
      </nav>

      <div class="reference-list">
        {#each purposes as purpose, index}
          <article class="reference-card purpose-card" id={purpose.slug}>
            <div class="reference-card-index" aria-hidden="true">{String(index + 1).padStart(2, '0')}</div>
            <div class="reference-card-content">
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
                <span class="iri-label">Purpose IRI</span>
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
                  <span class="chip-label">Refused with</span>
                  {#each purpose.denialCodes as code}
                    <a class="chip denial" href={`/problem-codes#${code}`}>{code}</a>
                  {/each}
                </div>
              {/if}

              {#if purpose.storyLinks.length}
                <div class="chip-row">
                  <span class="chip-label">Demonstrated in</span>
                  {#each purpose.storyLinks as link}
                    <a class="chip" href={`/stories/${link.storyId}#${link.stepId}`}>{link.storyTitle}: {link.stepLabel}</a>
                  {/each}
                </div>
              {/if}
            </div>
          </article>
        {/each}
      </div>

      <p class="back"><a href="/developers">Back to the developer workspace</a></p>
    </div>
  </section>
</main>
