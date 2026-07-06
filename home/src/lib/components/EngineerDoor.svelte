<script lang="ts">
  import type { CurlExample, PublishedToken } from '$lib/types';
  import CopyButton from '$lib/components/CopyButton.svelte';

  export let tokens: PublishedToken[] = [];
  export let curls: CurlExample[] = [];
  export let versions: Record<string, string> = {};
  export let repoUrl = 'https://github.com/registrystack/solmara-lab';

  const quickstart = ['just setup', 'just generate', 'just metadata-publish', 'just up', 'just smoke'];
</script>

<section class="page-band engineer" id="engineer-door">
  <div class="content">
    <p class="eyebrow">Engineer door</p>
    <h2>Clone to green smoke, then go off script</h2>

    <div class="engineer-columns">
      <div class="engineer-col">
        <h3>Five commands to a running country</h3>
        <pre>{quickstart.join('\n')}</pre>

        <h3>Reference and tooling</h3>
        <div class="engineer-links">
          <a href={`${repoUrl}/tree/main/requests`}>Bruno workspace</a>
          <a href="/metadata/catalog.json">Metadata catalog</a>
          <a href="/metadata/evidence-offerings.json">Evidence offerings</a>
          <a href="/problem-codes">Problem codes</a>
          <a href="https://docs.registrystack.org">Product docs and OpenAPI</a>
        </div>

        <h3>Pinned images</h3>
        <p class="pin"><span>Relay</span> <code>{versions.REGISTRY_RELAY_IMAGE ?? 'missing'}</code></p>
        <p class="pin"><span>Notary</span> <code>{versions.REGISTRY_NOTARY_IMAGE ?? 'missing'}</code></p>
      </div>

      <div class="engineer-col">
        <h3>Published demo tokens</h3>
        <p class="token-disclaimer">
          These are synthetic lab tokens, deliberately published. They only unlock the synthetic data
          on this lab and are safe to copy. Do not reuse this pattern for real credentials.
        </p>
        {#if tokens.length === 0}
          <p class="empty">No demo tokens are published on this deployment.</p>
        {:else}
          <div class="token-list">
            {#each tokens as token}
              <div class="token">
                <div class="token-head">
                  <strong>{token.name}</strong>
                  <CopyButton text={token.token} label="Copy token" />
                </div>
                <p class="token-note">{token.note}</p>
                <code class="token-value">{token.token}</code>
              </div>
            {/each}
          </div>
        {/if}

        <h3>Copy-as-curl</h3>
        <div class="curl-list">
          {#each curls as example}
            <div class="curl-example">
              <div class="curl-head">
                <strong>{example.title}</strong>
                <CopyButton text={example.command} label="Copy as curl" />
              </div>
              <p class="curl-note">{example.note}</p>
              <pre>{example.command}</pre>
            </div>
          {/each}
        </div>
      </div>
    </div>
  </div>
</section>
