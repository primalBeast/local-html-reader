/** Next index in a menu. A missing selection wraps to the end you are moving toward. */
export function nextMenuIndex(current: number, count: number, delta: number): number {
  if (count <= 0) return -1;
  if (current < 0) return delta < 0 ? count - 1 : 0;
  return (current + delta + count) % count;
}

export function menuItems(root: ParentNode): HTMLElement[] {
  return [...root.querySelectorAll<HTMLElement>('[data-menu-item]')].filter(
    (el) => !el.hasAttribute('disabled') && !el.hidden,
  );
}

export function moveMenuFocus(root: HTMLElement, delta: number) {
  const items = menuItems(root);
  if (!items.length) return;
  const active = document.activeElement;
  const current = items.findIndex((el) => el === active || el.contains(active));
  items[nextMenuIndex(current, items.length, delta)]?.focus();
}

export function focusFirstMenuItem(root: HTMLElement | null, prefer?: string) {
  if (!root) return;
  const items = menuItems(root);
  const chosen = prefer ? items.find((el) => el.matches(prefer)) : undefined;
  (chosen ?? items[0])?.focus();
}

export function onMenuKeydown(event: KeyboardEvent) {
  const root = event.currentTarget;
  if (!(root instanceof HTMLElement)) return;
  if (event.altKey || event.ctrlKey || event.metaKey) return;
  if (event.key === 'ArrowDown') {
    event.preventDefault();
    moveMenuFocus(root, 1);
  } else if (event.key === 'ArrowUp') {
    event.preventDefault();
    moveMenuFocus(root, -1);
  } else if (event.key === 'Home') {
    event.preventDefault();
    menuItems(root)[0]?.focus();
  } else if (event.key === 'End') {
    event.preventDefault();
    const items = menuItems(root);
    items[items.length - 1]?.focus();
  } else if (event.key === 'Enter' && event.target instanceof HTMLInputElement && event.target.type === 'checkbox') {
    event.preventDefault();
    event.target.click();
  }
}
