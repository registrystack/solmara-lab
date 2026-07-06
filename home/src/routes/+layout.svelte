<script lang="ts">
  import '../app.css';
  import SiteHeader from '$lib/components/SiteHeader.svelte';
  import SyntheticBanner from '$lib/components/SyntheticBanner.svelte';
  let { children } = $props();
</script>

<svelte:head>
  <link rel="icon" href="/favicon.svg" type="image/svg+xml" />
</svelte:head>

<SyntheticBanner />
<SiteHeader />
{@render children()}
