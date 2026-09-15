<script lang="ts">
  import { onMount } from 'svelte';

  let {
    x,
    y,
    onCopy,
    onClose,
  }: {
    x: number;
    y: number;
    onCopy: () => void | Promise<void>;
    onClose: () => void;
  } = $props();

  let el = $state<HTMLDivElement | null>(null);
  let left = $state(0);
  let top = $state(0);

  $effect(() => {
    let nextLeft = x;
    let nextTop = y;
    if (el) {
      const box = el.getBoundingClientRect();
      nextLeft = Math.max(8, Math.min(x, window.innerWidth - box.width - 8));
      nextTop = Math.max(8, Math.min(y, window.innerHeight - box.height - 8));
    }
    left = nextLeft;
    top = nextTop;
  });

  async function copy() {
    await onCopy();
    onClose();
  }

  onMount(() => {
    const close = (event: PointerEvent) => {
      if (el && event.target instanceof Node && el.contains(event.target)) return;
      onClose();
    };
    document.addEventListener('pointerdown', close, true);
    return () => document.removeEventListener('pointerdown', close, true);
  });
</script>

<div
  bind:this={el}
  class="path-menu"
  style={`left:${left}px;top:${top}px`}
  role="menu"
  aria-label="Copy"
>
  <button type="button" role="menuitem" onclick={() => void copy()}>Copy</button>
</div>
