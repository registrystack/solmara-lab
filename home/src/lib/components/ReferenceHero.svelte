<script lang="ts">
  type Fact = {
    value: string | number;
    label: string;
  };

  export let eyebrow: string;
  export let title: string;
  export let description: string;
  export let active: 'explorer' | 'purposes' | 'problem-codes' | 'anatomy' | 'changelog';
  export let facts: Fact[] = [];

  const references = [
    { id: 'explorer', href: '/explorer', label: 'Metadata' },
    { id: 'purposes', href: '/purposes', label: 'Purposes' },
    { id: 'problem-codes', href: '/problem-codes', label: 'Problem codes' },
    { id: 'anatomy', href: '/anatomy', label: 'Anatomy' },
    { id: 'changelog', href: '/changelog', label: 'Changelog' }
  ];
</script>

<section class="reference-hero">
  <div class="content reference-hero-grid">
    <div class="reference-hero-copy">
      <p class="eyebrow">{eyebrow}</p>
      <h1>{title}</h1>
      <p class="lede">{description}</p>

      {#if facts.length}
        <dl class="reference-facts">
          {#each facts as fact}
            <div>
              <dt>{fact.label}</dt>
              <dd>{fact.value}</dd>
            </div>
          {/each}
        </dl>
      {/if}
    </div>

    <aside class="reference-directory" aria-labelledby="reference-directory-title">
      <p class="eyebrow">Developer reference</p>
      <h2 id="reference-directory-title">Move between the published surface and its controls</h2>
      <nav aria-label="Developer reference pages">
        {#each references as reference}
          <a href={reference.href} aria-current={reference.id === active ? 'page' : undefined}>
            <span>{reference.label}</span>
            <span aria-hidden="true">→</span>
          </a>
        {/each}
      </nav>
      <a class="reference-workspace-link" href="/developers">Open the complete developer workspace</a>
    </aside>
  </div>
</section>
