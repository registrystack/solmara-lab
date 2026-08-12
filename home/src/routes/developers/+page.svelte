<script lang="ts">
  import EngineerDoor from '$lib/components/EngineerDoor.svelte';

  let { data } = $props();
  let home = $derived(data.home);
</script>

<svelte:head>
  <title>Developer workspace · Solmara Lab</title>
  <meta
    name="description"
    content="Run Solmara Lab locally, inspect its metadata and architecture, and reproduce permitted and refused requests."
  />
</svelte:head>

<main>
  <section class="page-band developer-page-intro">
    <div class="content">
      <p class="eyebrow">Developer workspace</p>
      <h1>Run the country, inspect every boundary</h1>
      <p class="lede">
        This is the complete technical surface behind the guided homepage: a clean-checkout journey,
        published metadata, source configuration, credential boundaries, and runnable requests.
      </p>
      <nav class="anchor-nav" aria-label="Developer references">
        <a href="/explorer">Metadata explorer</a>
        <a href="/purposes">Purpose register</a>
        <a href="/problem-codes">Problem codes</a>
        <a href="/anatomy">System anatomy</a>
        <a href="/status">Live status</a>
      </nav>
    </div>
  </section>

  <EngineerDoor
    curls={home.curlExamples}
    versions={home.versions}
    repoUrl={home.repoUrl}
  />
</main>
