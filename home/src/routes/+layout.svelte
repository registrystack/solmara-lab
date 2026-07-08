<script lang="ts">
  import '../app.css';
  import SiteHeader from '$lib/components/SiteHeader.svelte';
  import SyntheticBanner from '$lib/components/SyntheticBanner.svelte';
  let { children, data } = $props();
</script>

<svelte:head>
  <link rel="icon" href="/favicon.svg" type="image/svg+xml" />
  {#if data.analytics}
    <script async defer src={data.analytics.scriptUrl} data-website-id={data.analytics.websiteId}></script>
  {/if}
</svelte:head>

<SyntheticBanner />
<SiteHeader />
{@render children()}
