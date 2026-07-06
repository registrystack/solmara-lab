<script lang="ts">
  import type { ChangelogEntry, SeedSummary, SmokeEvidence, StatusItem } from '$lib/types';

  export let status: StatusItem[] = [];
  export let versions: Record<string, string> = {};
  export let smoke: SmokeEvidence = { available: false };
  export let seed: SeedSummary = { available: false };
  export let changelogLatest: ChangelogEntry | null = null;

  function shortDigest(value: string | undefined): string {
    if (!value) return 'missing';
    const at = value.indexOf('@');
    return at === -1 ? value : `${value.slice(0, at)}@${value.slice(at + 1, at + 20)}…`;
  }

  function smokeDate(timestamp: string | undefined): string {
    if (!timestamp) return '';
    return timestamp.replace('T', ' ').slice(0, 16) + ' UTC';
  }
</script>

<section class="trust" id="status">
  <div class="content">
    <p class="eyebrow">Live status</p>
    <p class="trust-note">
      Probed live from the server. An <strong>auth-gated</strong> service is up and correctly
      refusing anonymous reads (HTTP 401 or 403); that is the honest signal, not a failure.
    </p>
    <div class="status-grid">
      {#each status as item}
        {#if item.href}
          <a class={`status ${item.status}`} href={item.href}>
            <strong>{item.label}</strong>
            <span>{item.status}{item.httpStatus ? `, HTTP ${item.httpStatus}` : ''}</span>
          </a>
        {:else}
          <div class={`status ${item.status}`}>
            <strong>{item.label}</strong>
            <span>{item.status}{item.httpStatus ? `, HTTP ${item.httpStatus}` : ''}</span>
          </div>
        {/if}
      {/each}
    </div>

    <div class="trust-facts">
      <div>
        <p class="eyebrow">Pinned release</p>
        <p><strong>Relay</strong> <code>{shortDigest(versions.REGISTRY_RELAY_IMAGE)}</code></p>
        <p><strong>Notary</strong> <code>{shortDigest(versions.REGISTRY_NOTARY_IMAGE)}</code></p>
      </div>
      <div>
        <p class="eyebrow">Smoke evidence</p>
        {#if smoke.available}
          <p>Last smoke passed <strong>{smokeDate(smoke.timestamp)}</strong></p>
          <p><a href={smoke.href}>{smoke.file}</a></p>
        {:else}
          <p>No smoke evidence yet.</p>
        {/if}
      </div>
      <div>
        <p class="eyebrow">Data seed</p>
        {#if seed.available}
          <p>{seed.artifactCount ?? '?'} generated artifacts</p>
          {#if seed.observedAt}<p>Observed <strong>{seed.observedAt}</strong></p>{/if}
        {:else}
          <p>No seed summary found.</p>
        {/if}
      </div>
      <div>
        <p class="eyebrow">Changelog</p>
        {#if changelogLatest}
          <p><strong>{changelogLatest.date}</strong></p>
          <p><a href={changelogLatest.href}>{changelogLatest.title}</a></p>
        {:else}
          <p>No changelog yet.</p>
        {/if}
      </div>
    </div>

    <footer>
      <a href="https://docs.registrystack.org">Docs</a>
      <a href="https://github.com/registrystack">GitHub</a>
      <a href="https://github.com/registrystack/solmara-lab/blob/main/SECURITY.md">SECURITY.md</a>
    </footer>
  </div>
</section>
