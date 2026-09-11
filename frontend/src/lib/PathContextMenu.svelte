<script lang="ts">
  import { onMount } from 'svelte';

  let {
    x,
    y,
    full,
    rel,
    onClose,
  }: {
    x: number;
    y: number;
    full: string;
    rel: string;
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

  async function copy(text: string) {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.left = '-9999px';
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      ta.remove();
    }
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
  aria-label="Copy path"
>
  <button type="button" role="menuitem" onclick={() => void copy(full)}>Copy full path</button>
  <button type="button" role="menuitem" onclick={() => void copy(rel)}>Copy relative path</button>
</div>
