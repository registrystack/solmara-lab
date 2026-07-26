<script lang="ts">
  import { buildDistrictMap } from '$lib/districtMap';

  export let districts: any;
  export let provinces: any;
  export let country: any;

  $: map = buildDistrictMap({ districts, provinces, country });

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
