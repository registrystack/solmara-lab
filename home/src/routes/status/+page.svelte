<script lang="ts">
  import TrustStrip from '$lib/components/TrustStrip.svelte';

  let { data } = $props();
  let home = $derived(data.home);
</script>

<svelte:head>
  <title>Live status · Solmara Lab</title>
  <meta
    name="description"
    content="Topology-wide live status, release pins, smoke evidence, generated data evidence, and changelog for Solmara Lab."
  />
</svelte:head>

<main>
  <section class="page-band status-page-intro">
    <div class="content">
      <p class="eyebrow">Live status</p>
      <h1>Operational evidence for the whole lab</h1>
      <p class="lede">
        Every probe below runs from the server. An auth-gated response is healthy when a protected
        service correctly refuses an anonymous read.
      </p>
    </div>
  </section>

  <TrustStrip
    status={home.status}
    versions={home.versions}
    smoke={home.smoke}
    seed={home.seed}
    changelogLatest={home.changelogLatest}
  />
</main>
