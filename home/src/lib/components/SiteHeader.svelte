<script lang="ts">
  import { page } from '$app/stores';

  // Header nav shown on every page. Reference pages have their own routes;
  // Stories and Status are landing anchors because they live on the home page.
  const links = [
    { href: '/#stories', label: 'Stories' },
    { href: '/explorer', label: 'Explorer' },
    { href: '/purposes', label: 'Purposes' },
    { href: '/problem-codes', label: 'Problem codes' },
    { href: '/anatomy', label: 'Anatomy' },
    { href: '/#status', label: 'Status' }
  ];

  $: pathname = $page.url.pathname;

  function isCurrent(href: string): boolean {
    const [routePath] = href.split('#');
    if (routePath === '/' || routePath === '') return false;
    return pathname === routePath || pathname.startsWith(`${routePath}/`);
  }
</script>

<header class="topbar">
  <a class="brand" href="/">Solmara Visitor's Center</a>
  <nav aria-label="Visitor center pages">
    {#each links as link}
      <a href={link.href} aria-current={isCurrent(link.href) ? 'page' : undefined}>{link.label}</a>
    {/each}
  </nav>
</header>
