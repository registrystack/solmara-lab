<script lang="ts">
  import type { CurlExample } from '$lib/types';
  import CopyButton from '$lib/components/CopyButton.svelte';

  export let curls: CurlExample[] = [];
  export let versions: Record<string, string> = {};
  export let repoUrl = 'https://github.com/registrystack/solmara-lab';

  const quickstart = ['just setup', 'just up-generated', 'just smoke', 'just portal-live-e2e', 'just down'];
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
          <a href="/explorer">Published metadata explorer</a>
          <a href="/purposes">Purpose register</a>
          <a href="/anatomy">System anatomy</a>
          <a href={`${repoUrl}/tree/main/requests`}>Bruno workspace</a>
          <a href="/metadata/catalog.json">Metadata catalog</a>
          <a href="/metadata/evidence-offerings.json">Evidence offerings</a>
          <a href="/problem-codes">Problem codes</a>
          <a href="https://docs.registrystack.org">Product docs and OpenAPI</a>
        </div>

        <h3>Pinned release artifacts</h3>
        <p class="pin"><span>Registry Stack {versions.REGISTRY_STACK_SOURCE_REF || 'missing'}</span> <code>{versions.REGISTRY_STACK_SOURCE_COMMIT || 'missing'}</code></p>
        <p class="pin"><span>Evidence</span> <code>{versions.SOLMARA_EVIDENCE_IMAGE ?? 'missing'}</code></p>
        <p class="pin"><span>Mint</span> <code>{versions.SOLMARA_MINT_IMAGE ?? 'missing'}</code></p>
      </div>

      <div class="engineer-col">
        <h3>Credentials stay server-side</h3>
        <p class="token-disclaimer">
          Mint issues short-lived credentials to the programme and each authority service. The visitor
          center never publishes them. Curl examples use shell placeholders for your local credentials,
          nonce, and synthetic subject identifier.
        </p>

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
