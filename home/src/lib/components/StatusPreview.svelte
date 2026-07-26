<script lang="ts">
  import type { ChangelogEntry, SmokeEvidence, StatusItem } from '$lib/types';

  export let status: StatusItem[] = [];
  export let smoke: SmokeEvidence = { available: false };
  export let changelogLatest: ChangelogEntry | null = null;

  const visitorFacingIds = ['metadata', 'scenario-runner', 'portal', 'home'];

  $: healthy = status.filter((item) => item.status === 'up' || item.status === 'auth-gated').length;
  $: down = status.filter((item) => item.status === 'down').length;
  $: visitorFacing = visitorFacingIds
    .map((id) => status.find((item) => item.id === id))
    .filter((item): item is StatusItem => Boolean(item));

  function smokeDate(timestamp: string | undefined): string {
    if (!timestamp) return '';
    return timestamp.replace('T', ' ').slice(0, 16) + ' UTC';
  }
</script>

<section class="status-preview" id="status-preview">
  <div class="content">
    <div class="status-preview-head">
      <div>
        <p class="eyebrow">No. 07 · Live operational evidence</p>
        <h2>{healthy} of {status.length} checks are responding as expected</h2>
        <p>
          {#if down === 0}
            No service probe is currently down. Auth-gated endpoints are healthy when they correctly refuse anonymous reads.
          {:else}
            {down} service {down === 1 ? 'probe is' : 'probes are'} currently down.
          {/if}
        </p>
      </div>
      <a class="button-link secondary-link" href="/status">Open full live status</a>
    </div>

    <div class="status-preview-grid">
      {#each visitorFacing as item}
        <div class="status-summary {item.status}">
          <strong>{item.label}</strong>
          <span>{item.status}{item.httpStatus ? ` · HTTP ${item.httpStatus}` : ''}</span>
        </div>
      {/each}
      {#if smoke.available}
        <a class="status-summary evidence" href={smoke.href}>
          <strong>Latest smoke passed</strong>
          <span>{smokeDate(smoke.timestamp)}</span>
        </a>
      {/if}
      {#if changelogLatest}
        <a class="status-summary evidence" href={changelogLatest.href}>
          <strong>Latest change</strong>
          <span>{changelogLatest.date} · {changelogLatest.title}</span>
        </a>
      {/if}
    </div>
  </div>
</section>
