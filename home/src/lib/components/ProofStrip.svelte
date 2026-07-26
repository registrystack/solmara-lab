<script lang="ts">
  import type { MetadataBundle, Scenario } from '$lib/types';

  export let metadata: MetadataBundle;
  export let scenarios: Scenario[] = [];

  $: authorities = metadata.available
    ? new Set(metadata.catalog.datasets.map((dataset) => dataset.authority?.id ?? dataset.authority?.name).filter(Boolean)).size
    : null;
  $: registries = metadata.available
    ? metadata.catalog.datasets.length
    : null;
  $: journeys = scenarios.length || null;
</script>

<section class="proof-strip" id="proof" aria-label="Solmara Lab at a glance">
  <div class="content proof-grid">
    <div><strong>1</strong><span>synthetic country</span></div>
    <div><strong>{authorities ?? 'Unavailable'}</strong><span>live authorities</span></div>
    <div><strong>{registries ?? 'Unavailable'}</strong><span>live registries</span></div>
    <div><strong>{journeys ?? 'Unavailable'}</strong><span>guided policy journeys</span></div>
    <div><strong>0</strong><span>real resident records</span></div>
  </div>
</section>
