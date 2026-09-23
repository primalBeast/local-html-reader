<script lang="ts">
  import { onMount } from 'svelte';
  import type { SearchHistoryItem } from './api';

  let {
    value,
    placeholder,
    ariaLabel,
    history = [],
    searching = false,
    parallel = false,
    threadCount = 0,
    extraClass = '',
    onInput,
    onClear,
    onPick,
    onRemove,
    onCommitHistory,
    onSearch,
    onNext,
    onPrev,
    regex = false,
    matchCase = false,
    wholeWord = false,
    onRegexChange,
    onMatchCaseChange,
    onWholeWordChange,
    bindInput,
  }: {
    value: string;
    placeholder: string;
    ariaLabel: string;
    history?: SearchHistoryItem[];
    searching?: boolean;
    parallel?: boolean;
    threadCount?: number;
    extraClass?: string;
    onInput: (value: string) => void;
    onClear: () => void;
    onPick: (term: string, flags: { regex: boolean; matchCase: boolean; wholeWord: boolean }) => void;
    onRemove?: (term: string) => void;
    onCommitHistory?: (term: string, flags: { regex: boolean; matchCase: boolean; wholeWord: boolean }) => void;
    onSearch?: (value: string) => void;
    onNext?: () => void;
    onPrev?: () => void;
    regex?: boolean;
    matchCase?: boolean;
    wholeWord?: boolean;
    onRegexChange?: (value: boolean) => void;
    onMatchCaseChange?: (value: boolean) => void;
    onWholeWordChange?: (value: boolean) => void;
    bindInput?: (el: HTMLInputElement | null) => void;
  } = $props();

  let open = $state(false);
  let highlight = $state<number | null>(null);
  let wrapEl = $state<HTMLDivElement | null>(null);
  let listEl = $state<HTMLUListElement | null>(null);
  let committedOnDismiss = false;
  let lastSearched = '';

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

  function runSearch(raw?: string) {
    onSearch?.(raw ?? value);
  }

  function commitHistoryOnDismiss() {
    if (committedOnDismiss) return;
    committedOnDismiss = true;
    if (value !== lastSearched) {
      lastSearched = value;
      runSearch();
    }
    const term = value.trim();
    if (term) onCommitHistory?.(term, { regex, matchCase, wholeWord });
    closeList();
  }

  function isDocumentListTarget(target: EventTarget | null): boolean {
    return target instanceof Element && Boolean(target.closest('.tree, .search-workers'));
  }

  function closeIfOutside(target: EventTarget | null) {
    if (!wrapEl || !(target instanceof Node) || wrapEl.contains(target)) return;
    if (isDocumentListTarget(target)) {
      committedOnDismiss = true;
      closeList();
      return;
    }
    commitHistoryOnDismiss();
  }

  function onInputBlur(event: FocusEvent) {
    const next = event.relatedTarget;
    if (next instanceof Node && wrapEl?.contains(next)) return;
    if (isDocumentListTarget(next)) {
      committedOnDismiss = true;
      closeList();
      return;
    }
    requestAnimationFrame(() => {
      if (isDocumentListTarget(document.activeElement)) {
        committedOnDismiss = true;
        closeList();
        return;
      }
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

  function pickHistoryItem(item: SearchHistoryItem) {
    lastSearched = item.term;
    committedOnDismiss = true;
    closeList();
    onPick(item.term, {
      regex: item.regex,
      matchCase: item.matchCase,
      wholeWord: item.wholeWord,
    });
  }

  function applyHighlight() {
    if (highlight === null) return false;
    const item = history[highlight];
    if (!item) return false;
    pickHistoryItem(item);
    return true;
  }

  function toggleOpt(kind: 'regex' | 'matchCase' | 'wholeWord') {
    lastSearched = value;
    const next = {
      regex: kind === 'regex' ? !regex : regex,
      matchCase: kind === 'matchCase' ? !matchCase : matchCase,
      wholeWord: kind === 'wholeWord' ? !wholeWord : wholeWord,
    };
    if (kind === 'regex') onRegexChange?.(next.regex);
    else if (kind === 'matchCase') onMatchCaseChange?.(next.matchCase);
    else onWholeWordChange?.(next.wholeWord);
    const term = value.trim();
    if (term) onCommitHistory?.(term, next);
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
  <div class="search-field">
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
      lastSearched = '';
      closeList();
      onInput(e.currentTarget.value);
    }}
    onfocus={() => {
      committedOnDismiss = false;
      if (history.length) {
        open = true;
        highlight = null;
      }
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
        e.preventDefault();
        e.stopPropagation();
        closeList();
        return;
      }
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        e.stopPropagation();
        const historyShowing = open && history.length > 0;
        const down = e.key === 'ArrowDown';
        if (historyShowing) {
          moveHighlight(down ? 1 : -1);
          return;
        }
        if (down && onNext) {
          onNext();
          return;
        }
        if (!down && onPrev) {
          onPrev();
          return;
        }
        if (down) moveHighlight(1);
        else if (open) moveHighlight(-1);
        return;
      }
      if (e.key === 'Enter') {
        e.preventDefault();
        if (applyHighlight()) return;
        const typed = e.currentTarget.value;
        onInput(typed);
        if (onNext && typed === lastSearched && typed.trim()) {
          closeList();
          onNext();
          return;
        }
        lastSearched = typed;
        runSearch(typed);
        const term = typed.trim();
        if (term) onCommitHistory?.(term, { regex, matchCase, wholeWord });
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
    <div class="search-field-tools">
      <div class="search-opts">
        <button
          class="search-opt"
          class:on={matchCase}
          type="button"
          tabindex="-1"
          title={matchCase ? 'Match case on' : 'Match case off'}
          aria-pressed={matchCase}
          aria-label="Match case"
          onmousedown={(e) => {
            e.preventDefault();
            e.stopPropagation();
          }}
          onclick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            toggleOpt('matchCase');
          }}
        >Aa</button>
        <button
          class="search-opt"
          class:on={wholeWord}
          type="button"
          tabindex="-1"
          title={wholeWord ? 'Whole word on' : 'Whole word off'}
          aria-pressed={wholeWord}
          aria-label="Whole word"
          onmousedown={(e) => {
            e.preventDefault();
            e.stopPropagation();
          }}
          onclick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            toggleOpt('wholeWord');
          }}
        >W</button>
        <button
          class="search-opt"
          class:on={regex}
          type="button"
          tabindex="-1"
          title={regex ? 'Regular expression on' : 'Regular expression off'}
          aria-pressed={regex}
          aria-label="Regular expression"
          onmousedown={(e) => {
            e.preventDefault();
            e.stopPropagation();
          }}
          onclick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            toggleOpt('regex');
          }}
        >.*</button>
      </div>
      {#if searching}
        <span class="search-spinner" class:parallel aria-label="Searching" role="status"></span>
        {#if threadCount > 0}
          <span class="search-thread-count" class:parallel>{threadCount}</span>
        {/if}
      {/if}
      {#if value}
        <button class="search-clear" type="button" tabindex="-1" onclick={() => onClear()} aria-label="Clear search">×</button>
      {/if}
    </div>
  </div>
  {#if open && history.length}
    <ul class="search-history" bind:this={listEl} aria-label="Recent searches">
      {#each history as item, i (item.term)}
        <li class="search-history-row" class:active={highlight === i}>
          <button
            class="search-history-term"
            type="button"
            tabindex="-1"
            onmousedown={(e) => {
              e.preventDefault();
              e.stopPropagation();
            }}
            onclick={() => pickHistoryItem(item)}
          >
            {item.term}
            {#if item.matchCase}<span class="search-history-re" title="Match case">Aa</span>{/if}
            {#if item.wholeWord}<span class="search-history-re" title="Whole word">W</span>{/if}
            {#if item.regex}<span class="search-history-re" title="Regular expression">.*</span>{/if}
          </button>
          {#if onRemove}
            <button
              class="search-history-forget"
              type="button"
              tabindex="-1"
              aria-label="Remove {item.term} from history"
              onmousedown={(e) => {
                e.preventDefault();
                e.stopPropagation();
              }}
              onclick={(e) => {
                e.stopPropagation();
                onRemove(item.term);
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
