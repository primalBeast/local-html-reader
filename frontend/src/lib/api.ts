export type Root = {
  id: string;
  path: string;
  exists: boolean;
};

export type DocumentHit = {
  root_id: string;
  root_path: string;
  rel: string;
  name: string;
  size: number;
  mtime: number;
};

export type TreeNode = {
  name: string;
  rel: string;
  kind: 'dir' | 'file';
  root_id: string;
  root_path: string;
  size?: number;
  mtime?: number;
  children?: TreeNode[];
};

export type Settings = {
  schema_version: number;
  roots: Array<{ id: string; path: string }>;
  last_document: { root_id: string; rel: string } | null;
  sidebar_width: number;
  search_history: string[];
  page_search_history: string[];
  window: { last_host: string; last_port: number };
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
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
  settings: () => request<Settings>('/api/settings'),
  patchSettings: (body: Partial<Settings>) =>
    request<Settings>('/api/settings', { method: 'PATCH', body: JSON.stringify(body) }),
  addHistory: (bucket: 'search_history' | 'page_search_history', term: string) =>
    request<{ bucket: string; history: string[] }>('/api/settings/history', {
      method: 'POST',
      body: JSON.stringify({ bucket, term }),
    }),
  removeHistory: (bucket: 'search_history' | 'page_search_history', term: string) => {
    const params = new URLSearchParams({ bucket, term });
    return request<{ bucket: string; history: string[] }>(
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
  roots: () => request<{ roots: Root[] }>('/api/roots'),
  addRoot: (path: string) =>
    request<Root>('/api/roots', { method: 'POST', body: JSON.stringify({ path }) }),
  setRoot: (path: string) =>
    request<Root>('/api/roots', { method: 'PUT', body: JSON.stringify({ path }) }),
  removeRoot: (id: string) =>
    request<{ ok: boolean; id: string }>(`/api/roots/${encodeURIComponent(id)}`, {
      method: 'DELETE',
    }),
  documents: (q?: string, rootId?: string) => {
    const params = new URLSearchParams();
    if (q) params.set('q', q);
    if (rootId) params.set('root_id', rootId);
    const qs = params.toString();
    return request<{ documents: DocumentHit[]; truncated: boolean }>(
      `/api/documents${qs ? `?${qs}` : ''}`,
    );
  },
  tree: (q?: string, rootId?: string) => {
    const params = new URLSearchParams();
    if (q) params.set('q', q);
    if (rootId) params.set('root_id', rootId);
    const qs = params.toString();
    return request<{ tree: TreeNode[]; file_count: number; truncated: boolean; query: string }>(
      `/api/tree${qs ? `?${qs}` : ''}`,
    );
  },
};

export function viewUrl(rootId: string, rel: string): string {
  const parts = rel
    .replace(/\\/g, '/')
    .split('/')
    .filter(Boolean)
    .map(encodeURIComponent)
    .join('/');
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
