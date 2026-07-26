<script lang="ts">
  import type { Persona } from '$lib/types';
  import { personaOutcomeHref, personaOutcomes } from '$lib/personaOutcomes';

  export let personas: Persona[] = [];
  export let portalUrl = 'http://127.0.0.1:4300';

  const previewIds = ['2300010248', '2300036523', 'FR-1001'];

  $: byId = new Map(personas.map((persona) => [persona.roster_primary_id, persona]));
  $: previewPersonas = previewIds.map((id) => byId.get(id)).filter((persona): persona is Persona => Boolean(persona));
</script>

<section class="page-band citizen-preview" id="citizen-demo">
  <div class="content">
    <div class="section-intro split-intro">
      <div>
        <p class="eyebrow">No. 04 · Citizen demo</p>
        <h2>Open the portal as a synthetic person</h2>
      </div>
      <p>
        Follow a successful review, a deliberate refusal, or a farmer voucher path. These are fixed
        demo identities, not real residents.
      </p>
    </div>

    {#if previewPersonas.length === 0}
      <p class="empty">The synthetic persona roster is unavailable.</p>
    {:else}
      <div class="citizen-card-grid">
        {#each previewPersonas as persona (persona.roster_primary_id)}
          <article class="citizen-card">
            <p class="eyebrow">{persona.role}</p>
            <h3>{persona.given_name} {persona.family_name}</h3>
            {#each personaOutcomes(persona).slice(0, 1) as outcome}
              <p class="citizen-outcome tone-{outcome.tone}">{outcome.text}</p>
              <a class="story-outcome-link" href={personaOutcomeHref(outcome)}>See this outcome in the guided story</a>
            {/each}
            <a class="button-link secondary-link" href={`${portalUrl}/?persona=${persona.roster_primary_id}`}>
              Open the portal as {persona.given_name}
            </a>
          </article>
        {/each}
      </div>
    {/if}

    <p class="section-link"><a href="/country">Explore the full synthetic cast and country</a></p>
  </div>
</section>
