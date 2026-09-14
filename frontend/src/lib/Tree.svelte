<script lang="ts">
  import { nodeToHit, type DocumentHit, type TreeNode } from './api';

  let {
    nodes,
    selected,
    onOpen,
    onPathMenu,
  }: {
    nodes: TreeNode[];
    selected: DocumentHit | null;
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

  function moveSelection(delta: number) {
    const files = visibleFiles(nodes);
    if (!files.length) return;
    let index = files.findIndex((node) => isSelected(node));
    if (index < 0) index = delta > 0 ? -1 : files.length;
    const next = index + delta;
    if (next < 0 || next >= files.length) return;
    onOpen(nodeToHit(files[next]));
    requestAnimationFrame(() => {
      treeEl?.querySelector('.tree-row.file.active')?.scrollIntoView({ block: 'nearest' });
    });
  }

  function onTreeKeydown(event: KeyboardEvent) {
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      moveSelection(1);
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      moveSelection(-1);
    }
  }

  function openFile(node: TreeNode) {
    onOpen(nodeToHit(node));
    treeEl?.focus({ preventScroll: true });
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
        style={`padding-left: ${24 + depth * 14}px`}
        onclick={() => openFile(node)}
        oncontextmenu={(e) => onPathMenu?.(e, node)}
        title={node.rel}
      >
        {node.name}
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
