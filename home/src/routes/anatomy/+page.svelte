<script lang="ts">
  import type { TopologyGroup } from '$lib/types';
  import ReferenceHero from '$lib/components/ReferenceHero.svelte';

  export let data: { groups: TopologyGroup[]; composeServiceCount: number; repoUrl: string };
  $: groups = data.groups;
  $: serviceCount = groups.reduce((total, group) => total + group.services.length, 0);
  $: facts = [
    { value: groups.length, label: 'topology layers' },
    { value: serviceCount, label: 'documented services' },
    { value: data.composeServiceCount, label: 'Compose services' }
  ];
</script>

<svelte:head>
  <title>Anatomy · Solmara Lab</title>
  <meta name="description" content="What an institution actually runs: source-owned Records APIs, authority Evidence cells and Mint, application evidence collection, and the config linked in the repo." />
</svelte:head>

<main class="reference-surface reference-page">
  <ReferenceHero
    eyebrow="System anatomy"
    title="See where every trust boundary runs"
    description="Trace the deployed topology from source-owned registries and Records APIs through six authority Evidence cells to the applications that collect bounded signed values. Every card links back to the configuration that creates it."
    active="anatomy"
    {facts}
  />

  <section class="page-band reference-body">
    <div class="content">
      <nav class="section-index" aria-label="Topology layers">
        <span>Jump to a layer</span>
        {#each groups as group}
          <a href={`#${group.key}`}>{group.title}</a>
        {/each}
      </nav>

      <aside class="principle-callout">
        <p class="eyebrow">Sovereignty invariant</p>
        <strong>One authority, one source-owned boundary.</strong>
        <p>
          No authority hands its rows to a central store. Each keeps an independent accountability boundary, so
          a fault or compromise stays contained rather than becoming a country-wide data exposure.
        </p>
      </aside>

      {#each groups as group, index}
        <section class="topology-group" id={group.key}>
          <div class="topology-group-head">
            <span>{String(index + 1).padStart(2, '0')}</span>
            <div>
              <h2>{group.title}</h2>
              <p class="block-note">{group.blurb}</p>
            </div>
          </div>
          <div class="entity-grid">
            {#each group.services as service}
              <article class="entity topology-card" id={service.id}>
                <div class="entity-head">
                  <div>
                    <h3>{service.label}</h3>
                    {#if service.authority}<p class="attribution">{service.authority}</p>{/if}
                    {#if service.purpose}<p class="attribution">Purpose: {service.purpose}</p>{/if}
                  </div>
                </div>
                <p class="muted">{service.blurb}</p>
                <details class="config-drawer">
                  <summary>Open source configuration</summary>
                  <div class="config-links">
                    {#each service.config as link}
                      <a class="config-link" href={link.url}>
                        <strong>{link.label}</strong>
                        <code>{link.path}</code>
                      </a>
                    {/each}
                  </div>
                </details>
              </article>
            {/each}
          </div>
        </section>
      {/each}

      <p class="back"><a href="/developers">Back to the developer workspace</a></p>
    </div>
  </section>
</main>
