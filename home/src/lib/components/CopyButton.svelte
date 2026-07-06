<script lang="ts">
  export let text = '';
  export let label = 'Copy';
  let copied = false;
  let timer: ReturnType<typeof setTimeout> | undefined;

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      copied = true;
      clearTimeout(timer);
      timer = setTimeout(() => (copied = false), 1500);
    } catch {
      copied = false;
    }
  }
</script>

<button type="button" class="copy-button" on:click={copy}>{copied ? 'Copied' : label}</button>
