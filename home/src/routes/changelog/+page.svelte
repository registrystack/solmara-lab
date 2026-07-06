<script lang="ts">
  import type { ChangelogFullEntry } from '$lib/types';

  export let data: { entries: ChangelogFullEntry[]; repoUrl: string };
  $: entries = data.entries;
</script>

<svelte:head>
  <title>Changelog · Solmara Visitor's Center</title>
  <meta name="description" content="A small dated log of what changed in the Solmara visitor center and lab topology." />
</svelte:head>

<main class="page-band reference-page">
  <div class="content">
    <p class="eyebrow">Changelog</p>
    <h1>What changed, and when</h1>
    <p class="lede">
      A returning visitor can see the lab is alive here. The source of truth is
      <a href={`${data.repoUrl}/blob/main/docs/changelog.md`}>docs/changelog.md</a> in the repository.
    </p>

    {#if entries.length === 0}
      <p class="empty">No changelog entries yet.</p>
    {:else}
      <div class="reference-list">
        {#each entries as entry}
          <article class="reference-card">
            <p class="eyebrow">{entry.date}</p>
            <h2>{entry.title}</h2>
            {#if entry.body}<p class="plain">{entry.body}</p>{/if}
          </article>
        {/each}
      </div>
    {/if}

    <p class="back"><a href="/">Back to the Visitor's Center</a></p>
  </div>
</main>
