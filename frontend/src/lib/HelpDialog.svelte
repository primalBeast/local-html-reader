<script lang="ts">
  import { onMount } from 'svelte';
  import { api, type HelpDocument } from './api';

  let { onClose }: { onClose: () => void } = $props();
  let doc = $state<HelpDocument | null>(null);
  let error = $state('');

  onMount(() => {
    void api
      .help()
      .then((loaded) => {
        doc = loaded;
      })
      .catch(() => {
        error = 'Could not load help.';
      });
  });
</script>

<div
  class="modal-backdrop"
  onclick={(e) => {
    if (e.currentTarget === e.target) onClose();
  }}
  role="presentation"
>
  <div class="modal help-modal" role="dialog" aria-labelledby="help-title" aria-modal="true">
    <div class="help-head">
      <h2 id="help-title">Formats and limits</h2>
      <button class="btn-ghost btn-small" type="button" onclick={onClose}>Close</button>
    </div>
    <div class="help-scroll">
      {#if error}
        <p>{error}</p>
      {:else if !doc}
        <p>Loading…</p>
      {:else}
        <ul class="help-shared">
          {#each doc.shared as item (item.label)}
            <li><strong>{item.label}.</strong> {item.detail}</li>
          {/each}
        </ul>
        {#each doc.formats as format (format.name)}
          <section class="help-format">
            <h3>{format.name}</h3>
            <p class="help-ext">{format.extensions.join('  ')}</p>
            <ul>
              {#each format.limits as line, index (`${format.name}:${index}`)}
                <li>{line}</li>
              {/each}
            </ul>
          </section>
        {/each}
        <p class="help-skipped">{doc.skipped}</p>
      {/if}
    </div>
  </div>
</div>
