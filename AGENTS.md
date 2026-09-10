# Local HTML Reader — agent notes

## Tooling

- Use **uv only** for Python. Never system Python (`python`, `py`, `pip`).
- Commands: `uv sync`, `uv sync --extra dev`, `uv run lhr …`, `uv run pytest`.
- Shell is **PowerShell** on Windows.
- **GitHub MCP**, not `gh` CLI (not installed on this machine).

## Runtime

- Bind **127.0.0.1** only. Default port **8766**. No auth.
- Do not expose the port. Warn if `--host` is not loopback.
- Data dir is app settings/index only (`LHR_DATA_DIR` / `%OneDrive%\Local HTML Reader`). HTML files stay where they are on disk.
- Path sandbox: never serve or list files outside configured documents-root folders. Reject `..`, absolute paths, and symlink escapes.

## Frontend

- Svelte 5 + Vite 6 + TypeScript in `frontend/`.
- **Commit `frontend/dist`** after UI changes so clone-and-run works without Node.
- `.gitignore` must **not** ignore `frontend/dist`.
- GitHub MCP file commits choke above ~80–100k. Keep production JS split with `manualChunks` if bundles get large. Prefer `git push` over MCP file-by-file for `dist`.

## Windows

- `install.cmd` / `start.cmd` are double-click entrypoints.
- Refresh PATH for `%USERPROFILE%\.local\bin` (uv) before calling `uv`.
