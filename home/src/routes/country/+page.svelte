<script lang="ts">
  import NationPanel from '$lib/components/NationPanel.svelte';

  let { data } = $props();
  let home = $derived(data.home);
</script>

<svelte:head>
  <title>Explore the Republic of Solmara · Solmara Lab</title>
  <meta
    name="description"
    content="Explore Solmara's synthetic geography, live and future registries, and the fixed personas used by its guided stories."
  />
</svelte:head>

<main>
  <section class="page-band country-page-intro">
    <div class="content">
      <p class="eyebrow">The fictional setting</p>
      <h1>Explore the Republic of Solmara</h1>
      <p class="lede">
        Solmara provides a coherent synthetic country for end-to-end testing. Its map, people,
        authorities, and records are fictional. Its Registry Stack services and trust boundaries are live.
      </p>
    </div>
  </section>

  <NationPanel
    metadata={home.metadata}
    personas={home.personas}
    districts={home.districts}
    provinces={home.provinces}
    country={home.country}
    portalUrl={home.portalUrl}
  />
</main>
