<script lang="ts">
  import type { MetadataBundle, Scenario } from '$lib/types';

  export let metadata: MetadataBundle;
  export let scenarios: Scenario[] = [];

  $: authorities = metadata.available
    ? new Set(metadata.offerings.map((offering) => offering.issuing_authority?.id ?? offering.issuing_authority?.name).filter(Boolean)).size
    : null;
  $: evidenceCells = metadata.available
    ? metadata.catalog.data_services?.length ?? authorities
    : null;
  $: journeys = scenarios.length || null;
</script>

<section class="proof-strip" id="proof" aria-label="Solmara Lab at a glance">
  <div class="content proof-grid">
    <div><strong>1</strong><span>synthetic country</span></div>
    <div><strong>{authorities ?? 'Unavailable'}</strong><span>live authorities</span></div>
    <div><strong>{evidenceCells ?? 'Unavailable'}</strong><span>authority Evidence gateways</span></div>
    <div><strong>{journeys ?? 'Unavailable'}</strong><span>guided policy journeys</span></div>
    <div><strong>0</strong><span>real resident records</span></div>
  </div>
</section>
