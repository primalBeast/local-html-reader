<script lang="ts">
  import { onMount } from 'svelte';

  let {
    value,
    placeholder,
    ariaLabel,
    history = [],
    searching = false,
    extraClass = '',
    onInput,
    onClear,
    onPick,
    onRemove,
    onCommitHistory,
    onSearch,
    bindInput,
  }: {
    value: string;
    placeholder: string;
    ariaLabel: string;
    history?: string[];
    searching?: boolean;
    extraClass?: string;
    onInput: (value: string) => void;
    onClear: () => void;
    onPick: (term: string) => void;
    onRemove?: (term: string) => void;
    onCommitHistory?: (term: string) => void;
    onSearch?: (value: string) => void;
    bindInput?: (el: HTMLInputElement | null) => void;
  } = $props();

  let open = $state(false);
  let highlight = $state<number | null>(null);
  let wrapEl = $state<HTMLDivElement | null>(null);
  let listEl = $state<HTMLUListElement | null>(null);
  let committedOnDismiss = false;

  function bindField(node: HTMLInputElement) {
    bindInput?.(node);
    return {
      destroy() {
        bindInput?.(null);
      },
    };
  }

  function closeList() {
    open = false;
    highlight = null;
  }

  function runSearch() {
    onSearch?.(value);
  }

  function commitHistoryOnDismiss() {
    if (committedOnDismiss) return;
    committedOnDismiss = true;
    runSearch();
    const term = value.trim();
    if (term) onCommitHistory?.(term);
    closeList();
  }

  function closeIfOutside(target: EventTarget | null) {
    if (!wrapEl || !(target instanceof Node) || wrapEl.contains(target)) return;
    commitHistoryOnDismiss();
  }

  function onInputBlur() {
    requestAnimationFrame(() => {
      if (!wrapEl?.contains(document.activeElement)) commitHistoryOnDismiss();
    });
  }

  function moveHighlight(dir: 1 | -1) {
    if (history.length === 0) return;
    if (!open) {
      if (dir < 0) return;
      open = true;
      highlight = 0;
      return;
    }
    if (highlight === null) {
      highlight = 0;
      return;
    }
    highlight = Math.max(0, Math.min(history.length - 1, highlight + dir));
  }

  function applyHighlight() {
    if (highlight === null) return false;
    const term = history[highlight];
    if (!term) return false;
    closeList();
    onPick(term);
    return true;
  }

  $effect(() => {
    if (highlight === null) return;
    if (highlight >= history.length) {
      highlight = history.length ? history.length - 1 : null;
    }
  });

  $effect(() => {
    if (highlight === null || !listEl) return;
    const row = listEl.children[highlight] as HTMLElement | undefined;
    row?.scrollIntoView({ block: 'nearest' });
  });

  onMount(() => {
    const onPointerDown = (event: PointerEvent) => closeIfOutside(event.target);
    document.addEventListener('pointerdown', onPointerDown, true);
    return () => document.removeEventListener('pointerdown', onPointerDown, true);
  });
</script>

<div class="search-wrap {extraClass}" bind:this={wrapEl}>
  <input
    use:bindField
    type="text"
    {value}
    {placeholder}
    aria-label={ariaLabel}
    aria-autocomplete="list"
    autocomplete="off"
    spellcheck="false"
    class:has-clear={Boolean(value)}
    class:has-spinner={searching}
    oninput={(e) => {
      committedOnDismiss = false;
      closeList();
      onInput(e.currentTarget.value);
    }}
    onfocus={() => {
      committedOnDismiss = false;
    }}
    onpointerdown={(e) => {
      if (e.button === 0) {
        open = true;
        highlight = null;
      }
    }}
    onblur={onInputBlur}
    onkeydown={(e) => {
      if (e.key === 'Escape') {
        closeList();
        return;
      }
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        moveHighlight(1);
        return;
      }
      if (e.key === 'ArrowUp') {
        if (!open) return;
        e.preventDefault();
        moveHighlight(-1);
        return;
      }
      if (e.key === 'Enter') {
        e.preventDefault();
        if (applyHighlight()) return;
        runSearch();
        const term = value.trim();
        if (term) onCommitHistory?.(term);
        committedOnDismiss = true;
        closeList();
        return;
      }
      if (e.key === 'Tab') {
        e.preventDefault();
        const inputs = Array.from(document.querySelectorAll<HTMLInputElement>('.search-wrap input'));
        const index = inputs.indexOf(e.currentTarget);
        if (index < 0 || inputs.length === 0) return;
        const dir = e.shiftKey ? -1 : 1;
        const next = inputs[(index + dir + inputs.length) % inputs.length];
        next.focus();
        next.select();
      }
    }}
  />
  {#if searching}
    <span class="search-spinner" aria-label="Searching" role="status"></span>
  {/if}
  {#if value}
    <button class="search-clear" type="button" tabindex="-1" onclick={() => onClear()} aria-label="Clear search">×</button>
  {/if}
  {#if open && history.length}
    <ul class="search-history" bind:this={listEl} aria-label="Recent searches">
      {#each history as term, i (term)}
        <li class="search-history-row" class:active={highlight === i}>
          <button
            class="search-history-term"
            type="button"
            tabindex="-1"
            onmousedown={(e) => {
              e.preventDefault();
              e.stopPropagation();
            }}
            onclick={() => {
              closeList();
              onPick(term);
            }}
          >
            {term}
          </button>
          {#if onRemove}
            <button
              class="search-history-forget"
              type="button"
              tabindex="-1"
              aria-label="Remove {term} from history"
              onmousedown={(e) => {
                e.preventDefault();
                e.stopPropagation();
              }}
              onclick={(e) => {
                e.stopPropagation();
                onRemove(term);
              }}
            >
              ×
            </button>
          {/if}
        </li>
      {/each}
    </ul>
  {/if}
</div>
