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
</script>

{#snippet branch(items: TreeNode[], depth: number)}
  {#each items as node (`${node.root_id}:${node.kind}:${node.rel}`)}
    {#if node.kind === 'dir'}
      <div class="tree-row dir" style={`padding-left: ${8 + depth * 14}px`}>
        <button class="twist" type="button" onclick={(e) => toggle(node, e)} aria-label={isExpanded(node) ? 'Collapse' : 'Expand'}>
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
        style={`padding-left: ${24 + depth * 14}px`}
        onclick={() => onOpen(nodeToHit(node))}
        oncontextmenu={(e) => onPathMenu?.(e, node)}
        title={node.rel}
      >
        {node.name}
      </button>
    {/if}
  {/each}
{/snippet}

<div class="tree">
  {@render branch(nodes, 0)}
</div>
