<script lang="ts">
  import type { MetadataBundle, Persona } from '$lib/types';

  export let metadata: MetadataBundle;
  export let personas: Persona[] = [];
  export let districts: any;
  export let portalUrl = 'http://127.0.0.1:4300';

  $: paths = geoPaths(districts);
  $: liveRegistries = metadata.catalog.datasets;
  $: grayRegistries = metadata.catalog.gray_registries;

  function geoPaths(collection: any): string[] {
    const coordinates: number[][][] = [];
    for (const feature of collection?.features ?? []) {
      const geometry = feature.geometry;
      if (geometry?.type === 'Polygon') coordinates.push(...geometry.coordinates);
      if (geometry?.type === 'MultiPolygon') coordinates.push(...geometry.coordinates.flat());
    }
    const points = coordinates.flat();
    if (!points.length) return [];
    const xs = points.map((point) => point[0]);
    const ys = points.map((point) => point[1]);
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);
    const width = maxX - minX || 1;
    const height = maxY - minY || 1;
    return coordinates.map((ring) =>
      ring
        .map((point, index) => {
          const x = ((point[0] - minX) / width) * 360 + 20;
          const y = 260 - ((point[1] - minY) / height) * 220;
          return `${index === 0 ? 'M' : 'L'}${x.toFixed(1)} ${y.toFixed(1)}`;
        })
        .join(' ') + ' Z'
    );
  }
</script>

<section class="page-band nation" id="nation">
  <div class="content nation-grid">
    <div>
      <p class="eyebrow">The Nation</p>
      <h2>One island, six live authorities, ten future registries in view</h2>
      <svg class="map" viewBox="0 0 400 280" role="img" aria-label="Solmara district map rendered from committed GeoJSON">
        <rect x="0" y="0" width="400" height="280" fill="#dceef8" />
        {#each paths as path, index}
          <path d={path} class:index-even={index % 2 === 0} />
        {/each}
      </svg>
    </div>
    <div class="registry-grid">
      {#each liveRegistries as registry}
        <article class="registry live">
          <h3>{registry.title}</h3>
          <p>{registry.authority?.name}</p>
          <small>{registry.entities.length} entities, {registry.purposes.length} purposes</small>
        </article>
      {/each}
      {#each grayRegistries as registry}
        <article class="registry future">
          <h3>{registry.title}</h3>
          <p>{registry.owner}</p>
          <small>{registry.wave ? `Wave ${registry.wave}` : 'World bible only'}</small>
        </article>
      {/each}
    </div>
  </div>
  <div class="content persona-row">
    {#each personas.slice(0, 8) as persona}
      <a class="persona" href={`${portalUrl}/?persona=${persona.roster_primary_id}`}>
        <strong>{persona.given_name} {persona.family_name}</strong>
        <span>{persona.role}</span>
      </a>
    {/each}
  </div>
</section>
