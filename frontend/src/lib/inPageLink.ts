/** Hash to stay on, if this link points at the open file. Otherwise null. */
export function hashForSameFile(rawHref: string, resolvedHref: string, pageUrl: string): string | null {
  const raw = rawHref.trim();
  if (!raw || /^(?:javascript|mailto|data|blob|tel):/i.test(raw)) return null;
  if (/^(?:\.\/)?#/.test(raw)) return raw.slice(raw.indexOf('#'));

  let resolved: URL;
  let file: URL;
  try {
    resolved = new URL(resolvedHref);
    file = new URL(pageUrl, resolved);
  } catch {
    return null;
  }
  if (resolved.origin !== file.origin) return null;
  if (pathKey(resolved.pathname) !== pathKey(file.pathname)) return null;
  if (!resolved.hash) return null;
  return resolved.hash;
}

function pathKey(pathname: string): string {
  let text = pathname;
  try {
    text = decodeURIComponent(pathname);
  } catch {
    /* keep the raw path */
  }
  return text.replace(/\/+$/, '').toLowerCase();
}

/** Scroll to a fragment inside an open document, including srcdoc pages. */
export function revealHash(doc: Document, hash: string): void {
  const normalized = hash.startsWith('#') ? hash : `#${hash}`;
  const view = doc.defaultView;
  const base = doc.querySelector('base');
  const previous = base?.getAttribute('href');
  // A folder <base> would send "#section" to the server. Drop it for the jump.
  if (base && previous && !previous.startsWith('about:')) base.removeAttribute('href');
  try {
    if (view) view.location.hash = normalized;
  } catch {
    /* A srcdoc page can refuse a hash write. Scrolling still runs. */
  } finally {
    if (base && previous && base.getAttribute('href') !== previous) base.setAttribute('href', previous);
  }
  const bare = normalized.slice(1);
  if (!bare) {
    view?.scrollTo(0, 0);
    return;
  }
  let id = bare;
  try {
    id = decodeURIComponent(bare);
  } catch {
    /* keep the raw id */
  }
  const target = doc.getElementById(id) || doc.getElementsByName(id)[0] || null;
  if (target && 'scrollIntoView' in target) target.scrollIntoView({ block: 'start' });
}
