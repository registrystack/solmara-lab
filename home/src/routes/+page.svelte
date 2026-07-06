<script lang="ts">
  import NationPanel from '$lib/components/NationPanel.svelte';
  import PurposeLens from '$lib/components/PurposeLens.svelte';
  import EngineerDoor from '$lib/components/EngineerDoor.svelte';
  import TrustStrip from '$lib/components/TrustStrip.svelte';

  let { data } = $props();
  let home = $derived(data.home);
</script>

<svelte:head>
  <title>Republic of Solmara Visitor's Center</title>
  <meta
    name="description"
    content="Solmara Lab Visitor's Center for purpose-limited Registry Stack evidence flows."
  />
</svelte:head>

<main>
  <PurposeLens scenarios={home.scenarios} purposes={home.purposes} />

  <section class="page-band doors" id="doors">
    <div class="content">
      <div class="section-heading">
        <p class="eyebrow">Three doors</p>
        <h2>Choose the role you are visiting from</h2>
      </div>
      <div class="door-grid">
        <a class="door" href="#nation">
          <strong>Visit as a citizen</strong>
          <span>Fixed personas, memorable identifiers, and a handoff to the citizen portal.</span>
        </a>
        <a class="door" href="#stories">
          <strong>Visit as the relying agency</strong>
          <span>Run a guided story, see the denial, inspect the credential moment.</span>
        </a>
        <a class="door" href="#engineer-door">
          <strong>Visit as an engineer</strong>
          <span>Metadata, Bruno, OpenAPI links, demo tokens, and a five-command local path.</span>
        </a>
      </div>
    </div>
  </section>

  <section class="page-band stories" id="stories">
    <div class="content">
      <div class="section-heading">
        <p class="eyebrow">Guided stories</p>
        <h2>Three policy problems, each proven end to end</h2>
      </div>
      <div class="teaser-grid">
        {#if home.scenarios.length === 0}
          <p class="empty">Scenario runner is unavailable. Story cards will return when the service is healthy.</p>
        {/if}
        {#each home.scenarios as scenario}
          <a class="teaser" href={`/stories/${scenario.id}`}>
            <p class="eyebrow">{scenario.domain}</p>
            <h3>{scenario.short_title || scenario.title}</h3>
            <p class="teaser-proves">{scenario.proves}</p>
            <div class="standards">
              <span>DCI</span><span>PublicSchema</span><span>SD-JWT VC</span><span>CPSV-AP</span>
            </div>
            <span class="teaser-cta">Open the story</span>
          </a>
        {/each}
      </div>
    </div>
  </section>

  <NationPanel metadata={home.metadata} personas={home.personas} districts={home.districts} portalUrl={home.portalUrl} />

  <EngineerDoor tokens={home.publishedTokens} curls={home.curlExamples} versions={home.versions} repoUrl={home.repoUrl} />

  <TrustStrip
    status={home.status}
    versions={home.versions}
    smoke={home.smoke}
    seed={home.seed}
    changelogLatest={home.changelogLatest}
  />
</main>
