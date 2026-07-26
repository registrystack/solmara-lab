<script lang="ts">
  import LandingHero from '$lib/components/LandingHero.svelte';
  import ProofStrip from '$lib/components/ProofStrip.svelte';
  import HowItWorks from '$lib/components/HowItWorks.svelte';
  import PurposeLens from '$lib/components/PurposeLens.svelte';
  import CitizenPreview from '$lib/components/CitizenPreview.svelte';
  import DeveloperPreview from '$lib/components/DeveloperPreview.svelte';
  import SolmaraPreview from '$lib/components/SolmaraPreview.svelte';
  import StatusPreview from '$lib/components/StatusPreview.svelte';

  let { data } = $props();
  let home = $derived(data.home);

  const storyCopy: Record<string, { problem: string; boundary: string }> = {
    'birth-to-child-benefit': {
      problem: 'Review a child-benefit application without building a new family database.',
      boundary: 'Five source-owned facts return. Family records and poverty scores stay with their authorities.'
    },
    'death-to-pension-survivor': {
      problem: "Stop a deceased member's pension without disclosing their cause of death.",
      boundary: 'Life status is enough for the payment review. Sensitive civil-registration details stay private.'
    },
    'farmer-climate-smart-voucher': {
      problem: "Review a farmer voucher without exposing the farmer's complete record.",
      boundary: 'Voucher and livestock evidence are evaluated under separate purposes and separate boundaries.'
    }
  };
</script>

<svelte:head>
  <title>Solmara Lab · Purpose-limited government evidence, live</title>
  <meta
    name="description"
    content="A live synthetic country showing how public services request limited, purpose-bound evidence without copying source records."
  />
</svelte:head>

<main>
  <LandingHero />
  <ProofStrip metadata={home.metadata} scenarios={home.scenarios} />
  <HowItWorks />
  <PurposeLens scenarios={home.scenarios} purposes={home.purposes} />

  <section class="page-band stories" id="stories">
    <div class="content">
      <div class="section-intro split-intro">
        <div>
          <p class="eyebrow">Guided stories</p>
          <h2>Three policy problems, proven end to end</h2>
        </div>
        <p>
          Each story starts with a public-service problem, follows the real requests, and tests the
          boundary with a deliberate refusal.
        </p>
      </div>
      <div class="teaser-grid">
        {#if home.scenarios.length === 0}
          <p class="empty">The scenario runner is unavailable. Story cards will return when the service is healthy.</p>
        {/if}
        {#each home.scenarios as scenario}
          {@const copy = storyCopy[scenario.id] ?? { problem: scenario.short_title || scenario.title, boundary: scenario.proves }}
          <a class="teaser" href={`/stories/${scenario.id}`}>
            <p class="eyebrow">{scenario.domain}</p>
            <h3>{copy.problem}</h3>
            <p class="teaser-proves">{copy.boundary}</p>
            <span class="teaser-cta">Run this story</span>
          </a>
        {/each}
      </div>
    </div>
  </section>

  <CitizenPreview personas={home.personas} portalUrl={home.portalUrl} />
  <DeveloperPreview />
  <SolmaraPreview
    metadata={home.metadata}
    districts={home.districts}
    provinces={home.provinces}
    country={home.country}
  />
  <StatusPreview status={home.status} smoke={home.smoke} changelogLatest={home.changelogLatest} />
</main>
