<script lang="ts">
  import type { MetadataBundle, Persona } from '$lib/types';
  import { buildDistrictMap } from '$lib/districtMap';
  import { featuredPersonas, personaOutcomeHref, personaOutcomes } from '$lib/personaOutcomes';

  export let metadata: MetadataBundle;
  export let personas: Persona[] = [];
  export let districts: any;
  export let provinces: any;
  export let country: any;
  export let portalUrl = 'http://127.0.0.1:4300';

  $: map = buildDistrictMap({ districts, provinces, country });
  $: liveRegistries = metadata.catalog.datasets;
  $: grayRegistries = metadata.catalog.gray_registries;
  $: shownPersonas = featuredPersonas(personas);

  let activeDistrictCode: string | null = null;
  $: activeDistrict = map.districts.find((district) => district.code === activeDistrictCode) ?? null;
  $: mapCaption = activeDistrict
    ? `${activeDistrict.name} (${activeDistrict.code})${activeDistrict.provinceName ? `, ${activeDistrict.provinceName} province` : ''}`
    : 'Hover or focus a district to see its name and province.';

  function districtLabel(district: (typeof map.districts)[number]): string {
    return `${district.name}, admin code ${district.code}${district.provinceName ? `, ${district.provinceName} province` : ''}`;
  }

  function selectOnKey(event: KeyboardEvent, code: string) {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      activeDistrictCode = code;
    }
  }
</script>

<section class="page-band nation" id="nation">
  <div class="content nation-grid">
    <div>
      <p class="eyebrow">The Nation</p>
      <h2>One island, six live authorities, ten future registries in view</h2>
      <svg
        class="map"
        viewBox={`0 0 ${map.viewBoxWidth} ${map.viewBoxHeight}`}
        role="img"
        aria-labelledby="nation-map-title nation-map-desc"
      >
        <title id="nation-map-title">Map of the Republic of Solmara</title>
        <desc id="nation-map-desc">
          The nation's provinces and districts, rendered from the committed district boundary data. Hover or focus a
          district to see its name and province.
        </desc>
        <path class="coastline" d={map.coastlinePath} />
        {#each map.districts as district (district.code)}
          <g
            class="district-group"
            tabindex="0"
            role="button"
            aria-label={districtLabel(district)}
            aria-pressed={activeDistrictCode === district.code}
            on:mouseenter={() => (activeDistrictCode = district.code)}
            on:mouseleave={() => (activeDistrictCode = null)}
            on:focus={() => (activeDistrictCode = district.code)}
            on:blur={() => (activeDistrictCode = null)}
            on:click={() => (activeDistrictCode = district.code)}
            on:keydown={(event) => selectOnKey(event, district.code)}
          >
            <path
              class="district province-{district.provinceIndex} shade-{district.shadeIndex}"
              class:active={activeDistrictCode === district.code}
              d={district.path}
            />
            {#if district.labelFits}
              <text class="district-label" x={district.centroid.x} y={district.centroid.y}>{district.name}</text>
            {/if}
          </g>
        {/each}
      </svg>
      <p class="map-caption" aria-live="polite">{mapCaption}</p>
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
