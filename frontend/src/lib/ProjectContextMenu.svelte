<script lang="ts">
  import { onMount } from 'svelte';
  import { bindMenuDismiss } from './dismissMenu';

  let {
    x,
    y,
    name,
    onRename,
    onDelete,
    onClose,
  }: {
    x: number;
    y: number;
    name: string;
    onRename: () => void;
    onDelete: () => void;
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

  onMount(() => bindMenuDismiss(() => el, onClose));
</script>

<div
  bind:this={el}
  class="path-menu"
  style={`left:${left}px;top:${top}px`}
  role="menu"
  aria-label="Project actions for {name}"
>
  <button type="button" role="menuitem" onclick={onRename}>Rename…</button>
  <button type="button" role="menuitem" onclick={onDelete}>Delete…</button>
</div>
