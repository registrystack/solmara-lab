<script lang="ts">
  import type { MetadataBundle } from '$lib/types';
  import SolmaraMap from './SolmaraMap.svelte';

  export let metadata: MetadataBundle;
  export let districts: any;
  export let provinces: any;
  export let country: any;

  $: authorities = metadata.available
    ? new Set(metadata.catalog.datasets.map((dataset) => dataset.authority?.id ?? dataset.authority?.name).filter(Boolean)).size
    : null;
  $: registries = metadata.available
    ? metadata.catalog.datasets.reduce((total, dataset) => total + dataset.entities.length, 0)
    : null;
</script>

<section class="page-band solmara-preview" id="solmara-preview">
  <div class="content solmara-preview-grid">
    <div>
      <p class="eyebrow">The fictional setting</p>
      <h2>One synthetic country, with real working boundaries</h2>
      <p>
        The Republic of Solmara provides a coherent place, cast, and government for the lab. Its
        geography, people, authorities, and records are fictional. The services and trust
        boundaries are running code.
      </p>
      <dl class="country-facts">
        <div><dt>Live authorities</dt><dd>{authorities ?? 'Unavailable'}</dd></div>
        <div><dt>Live registries</dt><dd>{registries ?? 'Unavailable'}</dd></div>
        <div><dt>Real records</dt><dd>0</dd></div>
      </dl>
      <a class="button-link secondary-link" href="/country">Explore Solmara and its full synthetic cast</a>
    </div>
    <div class="preview-map">
      <SolmaraMap {districts} {provinces} {country} />
    </div>
  </div>
</section>
