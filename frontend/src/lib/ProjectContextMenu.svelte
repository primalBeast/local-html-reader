<script lang="ts">
  import { onMount } from 'svelte';
  import { bindMenuDismiss } from './dismissMenu';
  import { focusFirstMenuItem, onMenuKeydown } from './menuKeys';

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
  let askRemove = $state(false);

  $effect(() => {
    askRemove;
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

  onMount(() => {
    const off = bindMenuDismiss(() => el, onClose);
    queueMicrotask(() => focusFirstMenuItem(el));
    return off;
  });

  $effect(() => {
    if (!askRemove || !el) return;
    queueMicrotask(() => focusFirstMenuItem(el));
  });
</script>

<div
  bind:this={el}
  class="path-menu"
  class:menu-confirm-open={askRemove}
  style={`left:${left}px;top:${top}px`}
  role="menu"
  aria-label="Project actions for {name}"
  tabindex="-1"
  onkeydown={onMenuKeydown}
>
  {#if askRemove}
    <p class="menu-confirm">Remove project “{name}”? Folders on disk are not deleted.</p>
    <div class="menu-confirm-actions">
      <button type="button" data-menu-item onclick={() => (askRemove = false)}>Cancel</button>
      <button type="button" class="danger" data-menu-item onclick={onDelete}>Remove</button>
    </div>
  {:else}
    <button type="button" role="menuitem" data-menu-item onclick={onRename}>Rename…</button>
    <button type="button" role="menuitem" data-menu-item onclick={() => (askRemove = true)}>Remove project</button>
  {/if}
</div>
