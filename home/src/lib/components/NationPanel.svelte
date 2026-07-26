<script lang="ts">
  import type { MetadataBundle, Persona } from '$lib/types';
  import { featuredPersonas, personaOutcomeHref, personaOutcomes } from '$lib/personaOutcomes';
  import SolmaraMap from './SolmaraMap.svelte';

  export let metadata: MetadataBundle;
  export let personas: Persona[] = [];
  export let districts: any;
  export let provinces: any;
  export let country: any;
  export let portalUrl = 'http://127.0.0.1:4300';

  $: liveRegistries = metadata.catalog.datasets;
  $: grayRegistries = metadata.catalog.gray_registries;
  $: shownPersonas = featuredPersonas(personas);
</script>

<section class="page-band nation" id="nation">
  <div class="content nation-grid">
    <div>
      <p class="eyebrow">The Nation</p>
      <h2>One island, six live authorities, ten future registries in view</h2>
      <SolmaraMap {districts} {provinces} {country} />
    </div>
    <div class="registry-grid">
      {#each liveRegistries as registry}
        <article class="registry live">
          <h3>{registry.title}</h3>
          <p>{registry.authority?.name}</p>
          <small>{registry.entities.length} entities, {registry.purposes.length} purposes</small>
        </article>
      {/each}
      {#each grayRegistries as registry}
        <article class="registry future">
          <h3>{registry.title}</h3>
          <p>{registry.owner}</p>
          <small>{registry.wave ? `Wave ${registry.wave}` : 'World bible only'}</small>
        </article>
      {/each}
    </div>
  </div>
  <div class="content persona-row">
    {#each shownPersonas as persona (persona.roster_primary_id)}
      <article class="persona">
        <a class="persona-portal" href={`${portalUrl}/?persona=${persona.roster_primary_id}`}>
          <strong>{persona.given_name} {persona.family_name}</strong>
          <span>{persona.role}</span>
        </a>
        <ul class="persona-outcomes">
          {#each personaOutcomes(persona) as outcome}
            <li class="tone-{outcome.tone}">
              <a href={personaOutcomeHref(outcome)}>{outcome.text}</a>
            </li>
          {/each}
        </ul>
      </article>
    {/each}
  </div>
</section>
