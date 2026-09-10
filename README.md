# Local HTML Reader

A local-first web app for reading HTML documents that already live on your hard drive.
**No cloud, no upload, no account** — you point it at folders, it lists `.html` / `.htm`
files, and you read them in the browser.

HTML files stay where they are. The app data directory only stores settings (configured
folders and last-opened file).

## How to run (full install guide)

**Start here** — downloads, install steps, and troubleshooting:

| OS | Guide |
|----|--------|
| **Windows 11** | **[docs/RUN-Windows11.md](docs/RUN-Windows11.md)** |

## Requirements (summary)

- **Git** — to clone this repository
- **[uv](https://docs.astral.sh/uv/)** — installs Python 3.12+ and app dependencies
- A modern desktop browser (Edge, Chrome, Firefox)
- **Node.js 20+** only if you change the frontend source (production `frontend/dist` is committed)

> Do **not** use system Python. Always run via `uv`.

## Clone and run (short version)

```powershell
git clone https://github.com/primalBeast/local-html-reader.git
cd local-html-reader

# Install Python deps (creates .venv)
uv sync

# Start the local server and open the browser
uv run lhr serve --open
```

Then open [http://127.0.0.1:8766](http://127.0.0.1:8766) if it did not open automatically.

**Windows (double-click, after cloning):**

1. `install.cmd` — installs uv + app deps, then checks the install
2. `start.cmd` — starts the server and opens the browser

If you ever see `ModuleNotFoundError: No module named 'lhr'`:

```powershell
uv sync --reinstall
uv run lhr doctor
```

### First run

Add one or more **documents-root** folders (absolute Windows paths). The app recursively
lists `.html` / `.htm` under those roots. Click a file to view it.

### Data location

| Platform | Default data directory |
|----------|------------------------|
| Windows | `%OneDrive%\Local HTML Reader` (falls back to `%APPDATA%\LocalHtmlReader`) |
| macOS | `~/Library/Application Support/LocalHtmlReader` |
| Linux | `~/.local/share/local-html-reader` |

Override with:

```powershell
$env:LHR_DATA_DIR = "$HOME\MyHtmlReaderData"
uv run lhr serve --open
```

or `uv run lhr serve --data-dir path\to\data`.

### CLI

```powershell
uv run lhr serve --open          # start server (127.0.0.1:8766)
uv run lhr doctor                # diagnose install
```

## Frontend development

```powershell
# Install Node 20+ once, then:
cd frontend
npm ci
npm run dev          # Vite on :5173, proxies /api and /health to :8766
```

In another terminal:

```powershell
uv run lhr serve --reload   # enables CORS for Vite
```

Build and commit the production bundle (required for clone-and-run):

```powershell
cd frontend; npm ci; npm run build
# commit frontend/dist
```

## Security

- Binds to **127.0.0.1** by default (local only, no auth)
- Do **not** expose the port to the network without adding auth
- Path access is sandboxed under configured documents-root folders
- Prefer full-disk encryption (BitLocker) for data at rest

## Project layout

```text
lhr/                     Python package (FastAPI + CLI)
frontend/                Svelte 5 + Vite SPA
frontend/dist/           Committed production build (clone-and-run)
docs/RUN-Windows11.md    Install & run on Windows 11
tests/                   pytest suite
```

## Tests

```powershell
uv sync --extra dev
uv run pytest
```

## License

MIT
