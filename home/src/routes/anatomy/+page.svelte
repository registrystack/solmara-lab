<script lang="ts">
  import type { TopologyGroup } from '$lib/types';

  export let data: { groups: TopologyGroup[]; composeServiceCount: number; repoUrl: string };
  $: groups = data.groups;
</script>

<svelte:head>
  <title>Anatomy · Solmara Visitor's Center</title>
  <meta name="description" content="What an institution actually runs: one Relay and one Notary per authority, application evidence collection, and the entire config for each ministry linked in the repo." />
</svelte:head>

<main class="page-band reference-page">
  <div class="content">
    <p class="eyebrow">Anatomy</p>
    <h1>The whole country on a laptop</h1>
    <p class="lede">
      This is what a Solmara authority actually runs, parsed from the running compose topology. Every
      authority operates its own Relay (a read-only API over data it already holds) and source-owned
      Notaries certify minimized evidence close to those registries. Each ministry links to its
      entire configuration in the repository, so there is nothing hidden.
    </p>

    <p class="sovereignty">
      One Relay per authority is the sovereignty point: no authority hands its rows to a central
      store, each keeps its own independent audit chain, and a fault or compromise is contained to a
      single authority rather than the whole country.
    </p>

    {#each groups as group}
      <section class="topology-group" id={group.key}>
        <h2>{group.title}</h2>
        <p class="block-note">{group.blurb}</p>
        <div class="entity-grid">
          {#each group.services as service}
            <article class="entity" id={service.id}>
              <div class="entity-head">
                <div>
                  <h3>{service.label}</h3>
                  {#if service.authority}<p class="attribution">{service.authority}</p>{/if}
                  {#if service.purpose}<p class="attribution">Purpose: {service.purpose}</p>{/if}
                </div>
              </div>
              <p class="muted">{service.blurb}</p>
              <div class="config-links">
                <span class="chip-label">Entire config:</span>
                {#each service.config as link}
                  <a class="config-link" href={link.url}>
                    <strong>{link.label}</strong>
                    <code>{link.path}</code>
                  </a>
                {/each}
              </div>
            </article>
          {/each}
        </div>
      </section>
    {/each}

    <p class="back"><a href="/">Back to the Visitor's Center</a></p>
  </div>
</main>
