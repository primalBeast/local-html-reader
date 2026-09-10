# Run Local HTML Reader on Windows 11

Step-by-step guide to download everything you need and run the app in a browser on Windows 11.

The app is **100% local** — it does not upload your HTML files. It only reads folders you configure. On Windows it stores *settings* in your OneDrive folder so Windows can sync them if OneDrive is signed in. You only need a browser and a small Python toolchain.

---

## What you will install

| Tool | Required to run the app? | Why |
|------|--------------------------|-----|
| **Git for Windows** | Yes (to clone the repo) | Download the project source |
| **uv** | Yes | Installs Python 3.12+ and app dependencies |
| **A browser** | Yes | Edge is built into Windows 11; Chrome/Firefox also fine |
| **Node.js** | No (only if you edit the UI source) | Rebuild the frontend after code changes |

The production UI is already built and committed in `frontend/dist`, so **you do not need Node.js** just to run the app.

---

## Quick fix: `ModuleNotFoundError: No module named 'lhr.cli'`

The app package lives at the repo root (`lhr\cli.py`). Reinstall from a fresh pull:

```powershell
git pull
uv sync --reinstall
uv run lhr serve --open
```

Fallback — run as a module with PYTHONPATH set to the repo root:

```powershell
$env:PYTHONPATH = (Get-Location).Path
uv run python -m lhr serve --open
```

---

## 1. Install Git for Windows

1. Download the installer:  
   **[https://git-scm.com/download/win](https://git-scm.com/download/win)**
2. Run it. Defaults are fine for most people.
   - Recommended: enable **“Git from the command line and also from 3rd-party software”**
3. Close and reopen any open terminals after install.

Verify in **PowerShell** or **Windows Terminal**:

```powershell
git --version
```

---

## 2. Install uv (Python package runner)

**uv** downloads a modern Python and manages the app’s virtual environment. You do **not** need to install Python from python.org first.

### Option A — PowerShell (recommended)

Open **Windows Terminal** or **PowerShell** and run:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Close and reopen the terminal so `uv` is on your `PATH`.

### Option B — WinGet

```powershell
winget install --id=astral-sh.uv -e
```

Then reopen the terminal.

Verify:

```powershell
uv --version
```

Docs: [https://docs.astral.sh/uv/](https://docs.astral.sh/uv/)

> Avoid relying on random system Python installs. Always start this app with `uv run …`.

---

## 3. Clone the repository

In PowerShell:

```powershell
cd $HOME\Documents
git clone https://github.com/primalBeast/local-html-reader.git
cd local-html-reader
```

If you already have a copy:

```powershell
cd path\to\local-html-reader
git pull
```

---

## 4. Install the app (Python deps)

Easiest: double-click **`install.cmd`** in the repo folder. It installs **uv** if needed, runs `uv sync`, and checks that the app and UI bundle are present.

Or from the project root in PowerShell:

```powershell
uv sync
```

This creates a `.venv` folder and installs FastAPI, uvicorn, and the rest of the backend.

Optional health check:

```powershell
uv run lhr doctor
```

---

## 5. Start the web app

Easiest: double-click **`start.cmd`**. It starts the server and opens the browser. Leave that window open. If the app is already running, it just opens http://127.0.0.1:8766.

Or:

```powershell
uv run lhr serve --open
```

- Server binds to **http://127.0.0.1:8766** (local only)
- `--open` tries to open your default browser (Edge is fine)
- If the browser does not open, go to: [http://127.0.0.1:8766](http://127.0.0.1:8766)

Leave the PowerShell window open while you use the app. Stop the server with **Ctrl+C**.

### Daily start (after the first setup)

Double-click **`start.cmd`**, or:

```powershell
cd D:\dev\doc-reader   # your clone path
uv run lhr serve --open
```

---

## 6. First-run behavior

On first start the app has **no documents folder**. Open **Folder → Set root folder…** and paste an absolute Windows path (for example `D:\Notes\html`). The left pane shows that folder tree (`.html` / `.htm` only). Click a file to open it in the larger right pane.

The left search box looks **inside** HTML files and hides files that do not contain the text. The right-pane **Find in page** box searches only the open document (Ctrl+F).

HTML files are **not copied**. They stay on disk.

### Where settings are stored (Windows)

```text
%OneDrive%\Local HTML Reader\
```

Typical full path:

```text
C:\Users\<YourName>\OneDrive\Local HTML Reader\
```

An older AppData copy is moved here automatically on first start. If OneDrive is not available, the app falls back to `%APPDATA%\LocalHtmlReader\`.

Optional override (PowerShell session):

```powershell
$env:LHR_DATA_DIR = "$HOME\MyHtmlReaderData"
uv run lhr serve --open
```

---

## Optional: develop / rebuild the frontend

Only needed if you change files under `frontend\src\`.

1. Install **Node.js 20 LTS** from:  
   **[https://nodejs.org/](https://nodejs.org/)**  
   (or `winget install OpenJS.NodeJS.LTS`)
2. Rebuild:

   ```powershell
   cd frontend
   npm ci
   npm run build
   cd ..
   ```

3. Restart `uv run lhr serve --open`.

---

## Troubleshooting

| Problem | What to try |
|---------|-------------|
| `No module named 'lhr.cli'` | `git pull` then `uv sync --reinstall` |
| `uv` not recognized | Double-click `install.cmd`, or close and reopen Terminal; confirm with `uv --version` |
| Port already in use | `netstat -ano \| findstr :8766` then `taskkill /PID <pid> /F` |
| Blank or old UI | Hard refresh in Edge: **Ctrl+Shift+R** |
| Folder add fails | Path must be an existing **absolute** directory |

---

## Next

- Project overview: [../README.md](../README.md)
