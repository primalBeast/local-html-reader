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
    bindInput?: (el: HTMLInputElement | null) => void;
  } = $props();

  let open = $state(false);

  function bindField(node: HTMLInputElement) {
    bindInput?.(node);
    return {
      destroy() {
        bindInput?.(null);
      },
    };
  }

  function filtered(): string[] {
    const needle = value.trim().toLowerCase();
    if (!needle) return history;
    return history.filter((item) => item.toLowerCase().includes(needle));
  }

  onMount(() => {
    const close = () => {
      open = false;
    };
    window.addEventListener('click', close);
    return () => window.removeEventListener('click', close);
  });
</script>

<div class="search-wrap {extraClass}">
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
    oninput={(e) => onInput(e.currentTarget.value)}
    onfocus={() => {
      open = true;
    }}
    onclick={(e) => e.stopPropagation()}
    onkeydown={(e) => {
      if (e.key === 'Escape') open = false;
    }}
  />
  {#if searching}
    <span class="search-spinner" aria-label="Searching" role="status"></span>
  {/if}
  {#if value}
    <button class="search-clear" type="button" onclick={() => onClear()} aria-label="Clear search">×</button>
  {/if}
  {#if open && filtered().length}
    <ul class="search-history" aria-label="Recent searches">
      {#each filtered() as term (term)}
        <li>
          <button
            type="button"
            onmousedown={(e) => {
              e.preventDefault();
              e.stopPropagation();
            }}
            onclick={() => {
              open = false;
              onPick(term);
            }}
          >
            {term}
          </button>
        </li>
      {/each}
    </ul>
  {/if}
</div>
