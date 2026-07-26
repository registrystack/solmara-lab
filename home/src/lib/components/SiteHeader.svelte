<script lang="ts">
  import { page } from '$app/stores';

  // Keep the public navigation oriented around visitor intent. Detailed
  // references remain grouped under the developer workspace.
  const links = [
    { href: '/#how-it-works', label: 'How it works' },
    { href: '/#stories', label: 'Stories' },
    { href: '/#citizen-demo', label: 'Citizen demo' },
    { href: '/developers', label: 'Developers' },
    { href: '/status', label: 'Status' }
  ];

  $: pathname = $page.url.pathname;

  function isCurrent(href: string): boolean {
    const [routePath] = href.split('#');
    if (routePath === '/' || routePath === '') return false;
    return pathname === routePath || pathname.startsWith(`${routePath}/`);
  }
</script>

<header class="topbar">
  <a class="brand" href="/">Solmara Lab</a>
  <nav aria-label="Solmara Lab pages">
    {#each links as link}
      <a href={link.href} aria-current={isCurrent(link.href) ? 'page' : undefined}>{link.label}</a>
    {/each}
  </nav>
</header>
