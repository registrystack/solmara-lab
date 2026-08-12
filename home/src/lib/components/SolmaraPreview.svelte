<script lang="ts">
  import type { MetadataBundle } from '$lib/types';
  import SolmaraMap from './SolmaraMap.svelte';

  export let metadata: MetadataBundle;
  export let districts: any;
  export let provinces: any;
  export let country: any;

  $: authorities = metadata.available
    ? new Set(metadata.offerings.map((offering) => offering.issuing_authority?.id ?? offering.issuing_authority?.name).filter(Boolean)).size
    : null;
  $: evidenceCells = metadata.available
    ? metadata.catalog.data_services?.length ?? authorities
    : null;
</script>

<section class="page-band solmara-preview" id="solmara-preview">
  <div class="content solmara-preview-grid">
    <div>
      <p class="eyebrow">No. 06 · The fictional setting</p>
      <h2>One synthetic country, with real working boundaries</h2>
      <p>
        The Republic of Solmara provides a coherent place, cast, and government for the lab. Its
        geography, people, authorities, and records are fictional. The services and trust
        boundaries are running code.
      </p>
      <dl class="country-facts">
        <div><dt>Live authorities</dt><dd>{authorities ?? 'Unavailable'}</dd></div>
        <div><dt>Evidence cells</dt><dd>{evidenceCells ?? 'Unavailable'}</dd></div>
        <div><dt>Real records</dt><dd>0</dd></div>
      </dl>
      <a class="button-link secondary-link" href="/country">Explore Solmara and its full synthetic cast</a>
    </div>
    <div class="preview-map">
      <SolmaraMap {districts} {provinces} {country} />
    </div>
  </div>
</section>
