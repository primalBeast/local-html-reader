export type Root = {
  id: string;
  path: string;
  exists: boolean;
  enabled?: boolean;
};

export type ProjectFolder = {
  id: string;
  path: string;
  enabled: boolean;
  exists: boolean;
};

export type Project = {
  slug: string;
  name: string;
  folders: ProjectFolder[];
  last_document: { root_id: string; rel: string } | null;
};

export type DocumentHit = {
  root_id: string;
  root_path: string;
  rel: string;
  name: string;
  size: number;
  mtime: number;
};

export type SearchWorker = {
  slot: number;
  name: string;
  size: number;
};

export type TreeNode = {
  name: string;
  rel: string;
  kind: 'dir' | 'file';
  root_id: string;
  root_path: string;
  size?: number;
  mtime?: number;
  match_count?: number;
  children?: TreeNode[];
};

export type SearchHistoryItem = {
  term: string;
  regex: boolean;
  matchCase: boolean;
  wholeWord: boolean;
};

export type SearchFlags = { regex?: boolean; matchCase?: boolean; wholeWord?: boolean };

export function searchFlagsFromUnknown(raw: unknown): {
  regex: boolean;
  matchCase: boolean;
  wholeWord: boolean;
} {
  if (typeof raw === 'boolean') {
    return { regex: raw, matchCase: false, wholeWord: false };
  }
  if (raw && typeof raw === 'object') {
    const row = raw as {
      regex?: unknown;
      matchCase?: unknown;
      match_case?: unknown;
      wholeWord?: unknown;
      whole_word?: unknown;
    };
    return {
      regex: Boolean(row.regex),
      matchCase: Boolean(row.matchCase ?? row.match_case),
      wholeWord: Boolean(row.wholeWord ?? row.whole_word),
    };
  }
  return { regex: false, matchCase: false, wholeWord: false };
}

export function historyFromUnknown(
  raw: unknown,
  previous: SearchHistoryItem[] = [],
): SearchHistoryItem[] {
  if (!Array.isArray(raw)) return [];
  const prevByTerm = new Map(previous.map((row) => [row.term.toLowerCase(), row]));
  const out: SearchHistoryItem[] = [];
  const seen = new Set<string>();
  for (const item of raw) {
    let term = '';
    let flags = { regex: false, matchCase: false, wholeWord: false };
    if (typeof item === 'string') {
      term = item.trim();
      const prev = prevByTerm.get(term.toLowerCase());
      if (prev) flags = { regex: prev.regex, matchCase: prev.matchCase, wholeWord: prev.wholeWord };
    } else if (item && typeof item === 'object' && typeof (item as { term?: unknown }).term === 'string') {
      term = (item as { term: string }).term.trim();
      flags = searchFlagsFromUnknown(item);
    }
    if (!term) continue;
    const key = term.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push({ term, ...flags });
  }
  return out;
}

function applySearchFlags(params: URLSearchParams, flags?: SearchFlags): void {
  if (flags?.regex) params.set('use_regex', 'true');
  if (flags?.matchCase) params.set('match_case', 'true');
  if (flags?.wholeWord) params.set('whole_word', 'true');
}

export type Settings = {
  schema_version: number;
  roots: Array<{ id: string; path: string }>;
  last_document: { root_id: string; rel: string } | null;
  last_project_slug: string | null;
  projects_epoch: number;
  sidebar_width: number;
  search_history: SearchHistoryItem[];
  page_search_history: SearchHistoryItem[];
  window: { last_host: string; last_port: number };
};

let activeProject: string | null = null;

export function setApiProject(slug: string | null): void {
  activeProject = slug && slug.trim() ? slug.trim() : null;
}

export function getApiProject(): string | null {
  return activeProject;
}

function withProject(path: string): string {
  if (!activeProject) return path;
  const join = path.includes('?') ? '&' : '?';
  return `${path}${join}project=${encodeURIComponent(activeProject)}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(withProject(path), {
    ...init,
    headers: {
      Accept: 'application/json',
      ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
      ...init?.headers,
    },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body && typeof body.detail === 'string') detail = body.detail;
      else if (body && Array.isArray(body.detail)) detail = JSON.stringify(body.detail);
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return (await res.json()) as T;
}

export const api = {
  health: () => request<{ status: string; version: string }>('/health'),
  launchDocument: (rootId: string, rel: string) =>
    request<{ ok: boolean }>('/api/documents/launch', {
      method: 'POST',
      body: JSON.stringify({ root_id: rootId, rel }),
    }),
  settings: () => request<Settings>('/api/settings'),
  patchSettings: (body: Partial<Settings>) =>
    request<Settings>('/api/settings', { method: 'PATCH', body: JSON.stringify(body) }),
  addHistory: (
    bucket: 'search_history' | 'page_search_history',
    term: string,
    flags?: SearchFlags,
  ) =>
    request<{ bucket: string; history: SearchHistoryItem[] }>('/api/settings/history', {
      method: 'POST',
      body: JSON.stringify({
        bucket,
        term,
        regex: Boolean(flags?.regex),
        match_case: Boolean(flags?.matchCase),
        whole_word: Boolean(flags?.wholeWord),
      }),
    }),
  removeHistory: (bucket: 'search_history' | 'page_search_history', term: string) => {
    const params = new URLSearchParams({ bucket, term });
    return request<{ bucket: string; history: SearchHistoryItem[] }>(
      `/api/settings/history?${params.toString()}`,
      { method: 'DELETE' },
    );
  },
  watchSettings(onUpdate: (settings: Settings) => void): () => void {
    const source = new EventSource('/api/settings/events');
    source.onmessage = (event) => {
      try {
        onUpdate(JSON.parse(event.data) as Settings);
      } catch {
        /* ignore */
      }
    };
    return () => source.close();
  },
  projects: () => request<{ current_slug: string | null; projects: Project[] }>('/api/projects'),
  createProject: (name: string) =>
    request<Project>('/api/projects', { method: 'POST', body: JSON.stringify({ name }) }),
  selectProject: (slug: string) =>
    request<Project>(`/api/projects/${encodeURIComponent(slug)}/select`, { method: 'POST' }),
  renameProject: (slug: string, name: string) =>
    request<Project>(`/api/projects/${encodeURIComponent(slug)}`, {
      method: 'PATCH',
      body: JSON.stringify({ name }),
    }),
  deleteProject: (slug: string) =>
    request<{ ok: boolean; current_slug: string | null }>(
      `/api/projects/${encodeURIComponent(slug)}`,
      { method: 'DELETE' },
    ),
  addProjectFolder: (slug: string, path: string) =>
    request<ProjectFolder>(`/api/projects/${encodeURIComponent(slug)}/folders`, {
      method: 'POST',
      body: JSON.stringify({ path }),
    }),
  setFolderEnabled: (slug: string, folderId: string, enabled: boolean) =>
    request<ProjectFolder>(
      `/api/projects/${encodeURIComponent(slug)}/folders/${encodeURIComponent(folderId)}`,
      { method: 'PATCH', body: JSON.stringify({ enabled }) },
    ),
  removeProjectFolder: (slug: string, folderId: string) =>
    request<{ ok: boolean; id: string }>(
      `/api/projects/${encodeURIComponent(slug)}/folders/${encodeURIComponent(folderId)}`,
      { method: 'DELETE' },
    ),
  roots: () => request<{ roots: Root[] }>('/api/roots'),
  addRoot: (path: string) =>
    request<Root>('/api/roots', { method: 'POST', body: JSON.stringify({ path }) }),
  setRoot: (path: string) =>
    request<Root>('/api/roots', { method: 'PUT', body: JSON.stringify({ path }) }),
  setRootEnabled: (id: string, enabled: boolean) =>
    request<Root>(`/api/roots/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      body: JSON.stringify({ enabled }),
    }),
  removeRoot: (id: string) =>
    request<{ ok: boolean; id: string }>(`/api/roots/${encodeURIComponent(id)}`, {
      method: 'DELETE',
    }),
  documents: (q?: string, rootId?: string, flags?: SearchFlags) => {
    const params = new URLSearchParams();
    if (q) params.set('q', q);
    if (rootId) params.set('root_id', rootId);
    applySearchFlags(params, flags);
    const qs = params.toString();
    return request<{ documents: DocumentHit[]; truncated: boolean }>(
      `/api/documents${qs ? `?${qs}` : ''}`,
    );
  },
  tree: (q?: string, rootId?: string, flags?: SearchFlags) => {
    const params = new URLSearchParams();
    if (q) params.set('q', q);
    if (rootId) params.set('root_id', rootId);
    applySearchFlags(params, flags);
    const qs = params.toString();
    return request<{ tree: TreeNode[]; file_count: number; truncated: boolean; query: string }>(
      `/api/tree${qs ? `?${qs}` : ''}`,
    );
  },
  async treeStream(
    q: string | undefined,
    onProgress: (fileCount: number, tree?: TreeNode[], workers?: SearchWorker[]) => void,
    signal?: AbortSignal,
    flags?: SearchFlags,
  ): Promise<{ tree: TreeNode[]; file_count: number; truncated: boolean; query: string }> {
    const params = new URLSearchParams();
    if (q) params.set('q', q);
    applySearchFlags(params, flags);
    const qs = params.toString();
    const url = withProject(`/api/tree/stream${qs ? `?${qs}` : ''}`);
    return await readTreeSse(url, onProgress, signal);
  },
};

type TreeStreamResult = {
  tree: TreeNode[];
  file_count: number;
  truncated: boolean;
  query: string;
};

async function readTreeSse(
  url: string,
  onProgress: (fileCount: number, tree?: TreeNode[], workers?: SearchWorker[]) => void,
  signal?: AbortSignal,
): Promise<TreeStreamResult> {
  const res = await fetch(url, { signal, headers: { Accept: 'text/event-stream' } });
  if (!res.ok || !res.body) throw new Error(`tree stream failed (${res.status})`);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = '';
  let doneResult: TreeStreamResult | null = null;
  const consume = (block: string) => {
    let eventName = 'message';
    const dataLines: string[] = [];
    for (const line of block.split('\n')) {
      if (line.startsWith('event:')) eventName = line.slice(6).trim();
      else if (line.startsWith('data:')) dataLines.push(line.slice(5).replace(/^\s/, ''));
    }
    if (!dataLines.length) return;
    const data = JSON.parse(dataLines.join('\n')) as TreeStreamResult & {
      file_count?: number;
      detail?: string;
      workers?: SearchWorker[];
    };
    if (eventName === 'progress') onProgress(Number(data.file_count) || 0, data.tree, data.workers);
    else if (eventName === 'done') doneResult = data as TreeStreamResult;
    else if (eventName === 'fail') throw new Error(data.detail || 'tree stream failed');
  };
  while (true) {
    const chunk = await reader.read();
    if (chunk.done) break;
    buf += decoder.decode(chunk.value, { stream: true }).replace(/\r\n/g, '\n');
    const parts = buf.split('\n\n');
    buf = parts.pop() ?? '';
    for (const block of parts) consume(block);
  }
  if (buf.trim()) consume(buf);
  if (!doneResult) throw new Error('tree stream ended without results');
  return doneResult;
}

export function viewUrl(rootId: string, rel: string): string {
  const parts = rel
    .replace(/\\/g, '/')
    .split('/')
    .filter(Boolean)
    .map(encodeURIComponent)
    .join('/');
  // Do not append ?project= — HTML docs (Jazzy, etc.) treat the query string as
  // their own, and Edge can fail to load the iframe document for in-page search.
  return `/view/${encodeURIComponent(rootId)}/${parts}`;
}

export function windowsRelPath(rel: string): string {
  const text = (rel || '').replaceAll('/', '\\').replace(/^\\+/, '');
  return text || '.';
}

export function windowsFullPath(rootPath: string, rel: string): string {
  const root = (rootPath || '').replace(/[\\/]+$/, '');
  const relative = (rel || '').replaceAll('/', '\\').replace(/^\\+/, '');
  return relative ? `${root}\\${relative}` : root;
}

export function nodeToHit(node: TreeNode): DocumentHit {
  return {
    root_id: node.root_id,
    root_path: node.root_path,
    rel: node.rel,
    name: node.name,
    size: node.size ?? 0,
    mtime: node.mtime ?? 0,
  };
}
