/** Close a floating menu the way Windows does: click elsewhere, Escape, or scroll. */
export function bindMenuDismiss(el: () => HTMLElement | null, onClose: () => void): () => void {
  const close = () => onClose();

  const onPointerDown = (event: Event) => {
    const node = el();
    const target = event.target;
    if (node && target instanceof Node && node.contains(target)) return;
    close();
  };

  const onKeyDown = (event: KeyboardEvent) => {
    if (event.key === 'Escape') {
      event.preventDefault();
      close();
    }
  };

  const docs: Document[] = [document];
  const frames = Array.from(document.querySelectorAll('iframe'));
  for (const frame of frames) {
    try {
      const doc = frame.contentDocument;
      if (doc && doc !== document) docs.push(doc);
    } catch {
      /* cross-origin */
    }
  }

  for (const doc of docs) {
    doc.addEventListener('pointerdown', onPointerDown, true);
    doc.addEventListener('keydown', onKeyDown, true);
    doc.addEventListener('scroll', close, true);
  }
  window.addEventListener('blur', close);
  window.addEventListener('resize', close);

  return () => {
    for (const doc of docs) {
      doc.removeEventListener('pointerdown', onPointerDown, true);
      doc.removeEventListener('keydown', onKeyDown, true);
      doc.removeEventListener('scroll', close, true);
    }
    window.removeEventListener('blur', close);
    window.removeEventListener('resize', close);
  };
}
