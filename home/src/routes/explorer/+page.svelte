<script lang="ts">
  import type { MetadataBundle, MetadataOffering } from '$lib/types';
  import CopyButton from '$lib/components/CopyButton.svelte';

  export let data: { metadata: MetadataBundle; metadataBase: string };
  $: metadata = data.metadata;
  $: base = data.metadataBase.replace(/\/$/, '');
  $: apiItems = ((metadata.apiCatalog?.linkset as any[])?.[0]?.item ?? []) as { href: string; title: string; type: string }[];
  $: offeringsByAuthority = groupOfferings(metadata.offerings);
  $: policies = (metadata.policies ?? []) as any[];

  // Localise a single-language label object (e.g. {en: "..."}) to plain text.
  function label(value: unknown): string {
    if (typeof value === 'string') return value;
    if (value && typeof value === 'object') {
      const record = value as Record<string, string>;
      return record.en ?? Object.values(record)[0] ?? '';
    }
    return '';
  }

  function slug(iri: string): string {
    return iri.split('/').pop() ?? iri;
  }

  function rawUrl(pathSuffix: string): string {
    return `${base}${pathSuffix}`;
  }

  function curl(pathSuffix: string): string {
    return `curl -sS '${rawUrl(pathSuffix)}'`;
  }

  function groupOfferings(offerings: MetadataOffering[]): { authority: string; offerings: MetadataOffering[] }[] {
    const groups = new Map<string, MetadataOffering[]>();
    for (const offering of offerings) {
      const authority = offering.issuing_authority?.name ?? 'Unattributed authority';
      const list = groups.get(authority) ?? [];
      list.push(offering);
      groups.set(authority, list);
    }
    return [...groups.entries()].map(([authority, list]) => ({ authority, offerings: list }));
  }
</script>

<svelte:head>
  <title>Explorer · Solmara Visitor's Center</title>
  <meta name="description" content="The whole published Solmara metadata surface: catalog, datasets, services, evidence offerings, and policies." />
</svelte:head>

<main class="page-band explorer-page">
  <div class="content">
    <p class="eyebrow">Explorer</p>
    <h1>The whole published surface</h1>
    <p class="lede">
      Everything below is rendered straight from the published metadata bundle, the same bundle the
      Nation grid reads. Nothing here is hand-maintained. If the metadata service stops, this page
      degrades rather than showing stale data.
    </p>

    {#if !metadata.available}
      <p class="empty">Metadata service is unavailable, so the explorer is intentionally showing nothing rather than stale content.</p>
    {:else}
      <section class="explorer-block" id="api-catalog">
        <h2>Machine-readable catalog (api-catalog)</h2>
        <p class="block-note">The linkset an adopter's tooling discovers first. Each link is a raw artifact you can fetch.</p>
        <div class="artifact-list">
          {#each apiItems as item}
            <a href={item.href}>{item.title}<span>{item.type}</span></a>
          {/each}
        </div>
      </section>

      <section class="explorer-block" id="datasets">
        <h2>Datasets (DCAT)</h2>
        <p class="block-note">Each authority's dataset and the entities it exposes, with the purposes that may read them.</p>
        <div class="entity-grid">
          {#each metadata.catalog.datasets as dataset}
            <article class="entity">
              <div class="entity-head">
                <div>
                  <h3>{dataset.title}</h3>
                  <p class="muted">{dataset.description}</p>
                  {#if dataset.authority}<p class="attribution">{dataset.authority.name}</p>{/if}
                </div>
                <CopyButton text={curl('/metadata/dcat.jsonld')} label="Copy as curl" />
              </div>
              {#each dataset.entities as entity}
                <div class="entity-detail">
                  <strong>{entity.title}</strong>
                  {#if entity.semantics?.concepts?.length}
                    <p class="semantics">Semantics: {entity.semantics.concepts.join(', ')}</p>
                  {/if}
                  <div class="chip-row">
                    {#each entity.purposes as purpose}
                      <a class="chip" href={`/purposes#${slug(purpose)}`}>{slug(purpose)}</a>
                    {/each}
                  </div>
                </div>
              {/each}
              <a class="raw-link" href="/metadata/dcat.jsonld">Raw DCAT artifact</a>
            </article>
          {/each}
        </div>
      </section>

      <section class="explorer-block" id="services">
        <h2>Public services (CPSV-AP)</h2>
        <p class="block-note">The public services the evidence backs. Each names its competent authority and the evidence APIs it consumes.</p>
        <div class="entity-grid">
          {#each metadata.catalog.public_services as service}
            <article class="entity">
              <div class="entity-head">
                <div>
                  <h3>{label(service.title)}</h3>
                  <p class="muted">{label(service.description)}</p>
                  {#if service.competent_authority}<p class="attribution">Authority: {service.competent_authority}</p>{/if}
                </div>
                <CopyButton text={curl('/metadata/cpsv-ap.jsonld')} label="Copy as curl" />
              </div>
              {#if service.data_services?.length}
                <p class="semantics">Evidence APIs: {service.data_services.join(', ')}</p>
              {/if}
              <a class="raw-link" href="/metadata/cpsv-ap.jsonld">Raw CPSV-AP artifact</a>
            </article>
          {/each}
        </div>
      </section>

      <section class="explorer-block" id="offerings">
        <h2>Evidence offerings, by authority</h2>
        <p class="block-note">Each offering is a purpose-limited evidence product. It links to the policy that governs it and the purposes that may use it.</p>
        {#each offeringsByAuthority as group}
          <div class="authority-group">
            <h3 class="authority-name">{group.authority}</h3>
            <div class="entity-grid">
              {#each group.offerings as offering}
                <article class="entity" id={offering.id}>
                  <div class="entity-head">
                    <div>
                      <h4>{offering.title}</h4>
                      <p class="muted">{offering.description}</p>
                    </div>
                    <CopyButton text={curl(`/metadata/evidence-offerings/${offering.id}.json`)} label="Copy as curl" />
                  </div>
                  {#if offering.semantics?.concepts?.length}
                    <p class="semantics">Semantics: {offering.semantics.concepts.join(', ')}</p>
                  {/if}
                  <div class="chip-row">
                    {#each offering.purposes as purpose}
                      <a class="chip" href={`/purposes#${slug(purpose)}`}>{slug(purpose)}</a>
                    {/each}
                  </div>
                  <div class="cross-links">
                    {#if offering.policy}
                      <a href={`#policy-${offering.policy}`}>Governing policy</a>
                    {/if}
                    {#each offering.public_services ?? [] as svc}
                      <span class="cross-note">Backs service: {svc}</span>
                    {/each}
                    <a class="raw-link" href={`/metadata/evidence-offerings/${offering.id}.json`}>Raw artifact</a>
                  </div>
                </article>
              {/each}
            </div>
          </div>
        {/each}
      </section>

      <section class="explorer-block" id="policies">
        <h2>Policies (ODRL)</h2>
        <p class="block-note">The permission rules on each offering: which purposes are allowed to use it.</p>
        <div class="entity-grid">
          {#each policies as policy}
            <article class="entity" id={`policy-${policy.id}`}>
              <div class="entity-head">
                <div>
                  <h3>{policy.id}</h3>
                  <p class="muted">Target: {String(policy.target ?? '')}</p>
                </div>
                <CopyButton text={curl(`/metadata/policies/${policy.id}.jsonld`)} label="Copy as curl" />
              </div>
              {#each (policy.permission as any[]) ?? [] as permission}
                {#each permission.constraint ?? [] as constraint}
                  {#if constraint.leftOperand === 'purpose'}
                    <div class="chip-row">
                      {#each (constraint.rightOperand as string[]) ?? [] as purpose}
                        <a class="chip" href={`/purposes#${slug(purpose)}`}>{slug(purpose)}</a>
                      {/each}
                    </div>
                  {/if}
                {/each}
              {/each}
              <a class="raw-link" href={`/metadata/policies/${policy.id}.jsonld`}>Raw ODRL artifact</a>
            </article>
          {/each}
        </div>
      </section>
    {/if}

    <p class="back"><a href="/">Back to the Visitor's Center</a></p>
  </div>
</main>
