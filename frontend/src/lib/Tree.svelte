<script lang="ts">
  import { nodeToHit, type DocumentHit, type TreeNode } from './api';

  let {
    nodes,
    selected,
    openingKey = null,
    onOpen,
    onPathMenu,
  }: {
    nodes: TreeNode[];
    selected: DocumentHit | null;
    openingKey?: string | null;
    onOpen: (doc: DocumentHit) => void;
    onPathMenu?: (event: MouseEvent, node: TreeNode) => void;
  } = $props();

  let collapsed = $state<Record<string, boolean>>({});

  function dirKey(node: TreeNode): string {
    return `${node.root_id}:${node.rel}`;
  }

  function isExpanded(node: TreeNode): boolean {
    return !collapsed[dirKey(node)];
  }

  function toggle(node: TreeNode, event: MouseEvent) {
    event.stopPropagation();
    const key = dirKey(node);
    collapsed = { ...collapsed, [key]: !collapsed[key] };
  }

  function isSelected(node: TreeNode): boolean {
    return selected?.root_id === node.root_id && selected?.rel === node.rel;
  }

  let treeEl = $state<HTMLDivElement | null>(null);

  function visibleFiles(items: TreeNode[]): TreeNode[] {
    const out: TreeNode[] = [];
    const walk = (list: TreeNode[]) => {
      for (const node of list) {
        if (node.kind === 'file') out.push(node);
        else if (isExpanded(node) && node.children?.length) walk(node.children);
      }
    };
    walk(items);
    return out;
  }

  function selectFileAt(index: number, block: ScrollLogicalPosition = 'nearest') {
    const files = visibleFiles(nodes);
    if (!files.length) return;
    const next = Math.max(0, Math.min(files.length - 1, index));
    onOpen(nodeToHit(files[next]));
    requestAnimationFrame(() => {
      treeEl?.querySelector('.tree-row.file.active')?.scrollIntoView({ block });
    });
  }

  function moveSelection(delta: number) {
    const files = visibleFiles(nodes);
    if (!files.length) return;
    let index = files.findIndex((node) => isSelected(node));
    if (index < 0) index = delta > 0 ? -1 : files.length;
    const next = index + delta;
    if (next < 0 || next >= files.length) return;
    selectFileAt(next);
  }

  function scrollParent(): HTMLElement | null {
    return treeEl?.parentElement ?? null;
  }

  function visibleFileIndexes(): number[] {
    const scroller = scrollParent();
    const buttons = treeEl ? Array.from(treeEl.querySelectorAll<HTMLElement>('.tree-row.file')) : [];
    if (!scroller || !buttons.length) return [];
    const viewTop = scroller.scrollTop;
    const viewBottom = viewTop + scroller.clientHeight;
    const origin = scroller.getBoundingClientRect().top;
    const hits: number[] = [];
    for (let i = 0; i < buttons.length; i++) {
      const rect = buttons[i].getBoundingClientRect();
      const top = rect.top - origin + scroller.scrollTop;
      const bottom = top + rect.height;
      if (bottom > viewTop + 1 && top < viewBottom - 1) hits.push(i);
    }
    return hits;
  }

  function pageToEdge(edge: 'first' | 'last') {
    const files = visibleFiles(nodes);
    if (!files.length) return;
    const visible = visibleFileIndexes();
    const current = files.findIndex((node) => isSelected(node));
    const scroller = scrollParent();
    let target = edge === 'first' ? visible[0] : visible[visible.length - 1];
    const already = target === current;
    if (already && scroller) {
      const page = Math.max(24, scroller.clientHeight - 32);
      scroller.scrollTop += edge === 'last' ? page : -page;
      requestAnimationFrame(() => {
        const after = visibleFileIndexes();
        const idx = edge === 'first' ? after[0] : after[after.length - 1];
        selectFileAt(idx ?? (edge === 'first' ? 0 : files.length - 1), 'nearest');
      });
      return;
    }
    if (target == null) target = edge === 'first' ? 0 : files.length - 1;
    selectFileAt(target, 'nearest');
  }

  function onTreeKeydown(event: KeyboardEvent) {
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      moveSelection(1);
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      moveSelection(-1);
    } else if (event.key === 'Home') {
      event.preventDefault();
      const scroller = scrollParent();
      if (scroller) scroller.scrollTop = 0;
      const files = visibleFiles(nodes);
      if (files.length) onOpen(nodeToHit(files[0]));
    } else if (event.key === 'End') {
      event.preventDefault();
      selectFileAt(visibleFiles(nodes).length - 1, 'end');
    } else if (event.key === 'PageDown') {
      event.preventDefault();
      pageToEdge('last');
    } else if (event.key === 'PageUp') {
      event.preventDefault();
      pageToEdge('first');
    }
  }

  function openFile(node: TreeNode) {
    onOpen(nodeToHit(node));
    treeEl?.focus({ preventScroll: true });
  }

  function formatMb(bytes: number | undefined): string {
    const mb = (bytes ?? 0) / (1024 * 1024);
    if (mb < 1) return `${mb.toFixed(1)} MB`;
    return `${Math.round(mb)} MB`;
  }
</script>

{#snippet branch(items: TreeNode[], depth: number)}
  {#each items as node (`${node.root_id}:${node.kind}:${node.rel}`)}
    {#if node.kind === 'dir'}
      <div class="tree-row dir" style={`padding-left: ${8 + depth * 14}px`}>
        <button class="twist" type="button" tabindex="-1" onclick={(e) => toggle(node, e)} aria-label={isExpanded(node) ? 'Collapse' : 'Expand'}>
          {isExpanded(node) ? '▾' : '▸'}
        </button>
        <!-- svelte-ignore a11y_no_static_element_interactions -->
        <span
          class="folder-name"
          title={node.root_path}
          oncontextmenu={(e) => onPathMenu?.(e, node)}
        >{node.name}</span>
      </div>
      {#if isExpanded(node) && node.children?.length}
        {@render branch(node.children, depth + 1)}
      {/if}
    {:else}
      <button
        class="tree-row file"
        class:active={isSelected(node)}
        type="button"
        tabindex="-1"
        role="treeitem"
        aria-selected={isSelected(node)}
        style={`padding-left: ${node.match_count ? 4 : 24 + depth * 14}px`}
        onclick={() => openFile(node)}
        oncontextmenu={(e) => onPathMenu?.(e, node)}
        title={`${node.rel} (${formatMb(node.size)})${node.match_count ? `, ${node.match_count} matches` : ''}`}
      >
        {#if node.match_count}
          <span class="file-matches">{node.match_count}</span>
          <span class="file-indent" style={`width: ${depth * 14}px`}></span>
        {/if}
        <span class="file-name">{node.name}</span>
        {#if openingKey === `${node.root_id}:${node.rel}`}
          <span class="file-open-spinner" role="status" aria-label="Loading file"></span>
        {/if}
        <span class="file-size">{formatMb(node.size)}</span>
      </button>
    {/if}
  {/each}
{/snippet}

<div
  class="tree"
  bind:this={treeEl}
  tabindex="0"
  role="tree"
  aria-label="Documents"
  onkeydown={onTreeKeydown}
>
  {@render branch(nodes, 0)}
</div>
