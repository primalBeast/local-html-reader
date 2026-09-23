export type FindFlags = { regex?: boolean; matchCase?: boolean; wholeWord?: boolean };
export type TextHit = { start: number; end: number };

export function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

export function hitsInText(text: string, query: string, flags: FindFlags): TextHit[] {
  const hits: TextHit[] = [];
  const q = query.trim();
  if (!q || !text) return hits;
  let source = flags.regex ? q : escapeRegExp(q);
  if (flags.wholeWord) {
    source = `(?<![\\p{L}\\p{N}_])(?:${source})(?![\\p{L}\\p{N}_])`;
  }
  let re: RegExp;
  try {
    re = new RegExp(source, `${flags.matchCase ? '' : 'i'}gu`);
  } catch {
    return hits;
  }
  let match: RegExpExecArray | null;
  while ((match = re.exec(text)) !== null) {
    if (!match[0].length) {
      re.lastIndex += 1;
      continue;
    }
    hits.push({ start: match.index, end: match.index + match[0].length });
    if (hits.length >= 8000) break;
  }
  return hits;
}

export type TextSlice = { from: number; to: number; sliceFrom: number; sliceTo: number };

/** Split [0, length) into `parts` ranges. Each slice includes pad so a match can cross the cut. */
export function textSlices(length: number, parts: number, pad: number): TextSlice[] {
  const count = Math.max(1, Math.min(parts, length));
  const size = Math.ceil(length / count);
  const out: TextSlice[] = [];
  for (let i = 0; i < count; i++) {
    const from = i * size;
    if (from >= length) break;
    const to = Math.min(length, from + size);
    out.push({
      from,
      to,
      sliceFrom: Math.max(0, from - pad),
      sliceTo: Math.min(length, to + pad),
    });
  }
  return out;
}

export function workerCountFor(textLength: number): number {
  const cpu = Math.max(2, (globalThis.navigator?.hardwareConcurrency || 8) - 1);
  if (textLength < 80_000) return 1;
  return Math.max(1, Math.min(cpu, Math.floor(textLength / 80_000)));
}
