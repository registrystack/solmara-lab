<script lang="ts">
  import type { ChangelogFullEntry } from '$lib/types';
  import ReferenceHero from '$lib/components/ReferenceHero.svelte';

  export let data: { entries: ChangelogFullEntry[]; repoUrl: string };
  $: entries = data.entries;
  $: facts = [
    { value: entries.length, label: 'documented releases' },
    { value: entries[0]?.date ?? 'None yet', label: 'latest change' },
    { value: 'Git', label: 'source of truth' }
  ];

  function summary(body: string): string {
    if (body.length <= 300) return body;
    const sentences = body.match(/[^.!?]+[.!?]+/g) ?? [];
    let excerpt = '';
    for (const sentence of sentences) {
      if (excerpt && excerpt.length + sentence.length > 300) break;
      excerpt += sentence;
    }
    return excerpt.trim() || `${body.slice(0, 297).trim()}…`;
  }
</script>

<svelte:head>
  <title>Changelog · Solmara Lab</title>
  <meta name="description" content="A small dated log of what changed in Solmara Lab and its topology." />
</svelte:head>

<main class="reference-surface reference-page">
  <ReferenceHero
    eyebrow="Changelog"
    title="Follow the lab as it evolves"
    description="See the dated product and topology changes that affect what the demonstrations prove. The concise timeline stays readable here, while the repository remains the complete source of truth."
    active="changelog"
    {facts}
  />

  <section class="page-band reference-body">
    <div class="content">
      <div class="changelog-source">
        <div>
          <p class="eyebrow">Canonical record</p>
          <strong>Every entry is committed with the code it describes.</strong>
        </div>
        <a class="button-link secondary-link" href={`${data.repoUrl}/blob/main/docs/changelog.md`}>Open docs/changelog.md</a>
      </div>

      {#if entries.length === 0}
        <p class="empty">No changelog entries yet.</p>
      {:else}
        <div class="change-timeline">
          {#each entries as entry, index}
            <article class="change-entry" class:latest={index === 0}>
              <div class="change-marker" aria-hidden="true"></div>
              <div class="change-card">
                <div class="change-head">
                  <p class="eyebrow">{entry.date}</p>
                  {#if index === 0}<span>Latest</span>{/if}
                </div>
                <h2>{entry.title}</h2>
                {#if entry.body}
                  <p class="change-summary">{summary(entry.body)}</p>
                  {#if summary(entry.body) !== entry.body}
                    <details class="change-detail">
                      <summary>Read the full release note</summary>
                      <p>{entry.body}</p>
                    </details>
                  {/if}
                {/if}
              </div>
            </article>
          {/each}
        </div>
      {/if}

      <p class="back"><a href="/developers">Back to the developer workspace</a></p>
    </div>
  </section>
</main>
