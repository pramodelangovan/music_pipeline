<p align="center"><img src="https://raw.githubusercontent.com/pramodelangovan/music_pipeline/refs/heads/main/resources/music-pipeline.svg" alt="Music Pipeline logo" width="160"></p>

# Music Pipeline

Music Pipeline downloads YouTube music (single videos or whole playlists) as MP3/video through a download queue, tags audio with metadata and cover art, and keeps a history of every job.

It ships as two tools that share the same engine (`core/`):

| Tool | What it is | Run it with |
|------|------------|-------------|
| **Desktop app** | PySide6 window, runs the queue in-process | `tools\build.ps1 desktop` (or run from source) |
| **Web app** | FastAPI backend + React UI in Docker | `tools\build.ps1 web` / `web-build` |

---

## 1. One-time setup (both tools)

1. Get the code and open a terminal in the project root.
2. Run the setup script. It installs Python, ffmpeg and Deno, creates `.venv` if it does not exist, and installs every Python requirement:
   - Windows: `powershell -ExecutionPolicy Bypass -File tools\setup.ps1`
   - Linux/macOS: `bash tools/setup.sh`
3. Export your YouTube cookies (YouTube often asks for a login):
   1. Install the Chrome extension **Get cookies.txt LOCALLY**.
   2. Open YouTube while signed in and export the cookies.
   3. Save the file as `cookies.txt` in the project root (or upload it later in the Settings tab).

> Only the web app deployed with Docker can skip step 2: the Docker images already contain everything. You only need Docker.

---

## 2. Desktop app

### Build

1. Complete the setup above.
2. Run the build:
   - Windows: `powershell -ExecutionPolicy Bypass -File tools\build.ps1 desktop`
   - Linux/macOS: `bash tools/build.sh desktop`
3. The app is created as a single file: `dist\MusicPipeline.exe` (Linux/macOS: `dist/MusicPipeline`).
4. Copy that one file anywhere and run it. Downloads go to a `downloads` folder in the directory you launch it from.
5. Logs, history and `cookies.txt` are stored in your user folder (`%LOCALAPPDATA%\MusicPipeline` on Windows, `~/.local/share/MusicPipeline` on Linux, `~/Library/Application Support/MusicPipeline` on macOS). Use **Settings → Open Logs Folder** to view them.

### Run from source (no build)

1. Activate the environment: `.venv\Scripts\Activate.ps1` (Linux/macOS: `source .venv/bin/activate`).
2. Start the app: `python apps/desktop/main.py`.

### Use

1. Open **Settings**: set the gap between downloads and import `cookies.txt`.
2. Open **Queue**: add one or more rows (URL, audio/video, target folder) and click **Queue Downloads**.
3. Click **Start Queue** to begin, **Pause Queue** to pause. Playlists are expanded into one job per track.
4. **Retry Failed** re-queues failed items; **Clear Completed** hides successful items from the Queue view; **Clear All** hides every finished item (queued/active ones stay). History is kept.
5. Open **Research** to search for music, tick the results, choose Audio or Video per row and click **Queue Selected**.
6. Open **History** to see every past job; **Clear History** deletes finished/failed entries (queued and active jobs stay).

If ffmpeg or Deno is missing at runtime, the app installs them automatically.

---

## 3. Web app (Docker)

Requirements: Docker with Compose v2, and the Docker daemon running.

### Option A: build and deploy on this machine

1. Run:
   - Windows: `powershell -ExecutionPolicy Bypass -File tools\build.ps1 web`
   - Linux/macOS: `bash tools/build.sh web`
2. Open the UI at `http://localhost:3000` (API at `http://localhost:8000`).
3. Stop with `docker compose down`.

### Option B: build a package and deploy elsewhere

1. Run:
   - Windows: `powershell -ExecutionPolicy Bypass -File tools\build.ps1 web-build`
   - Linux/macOS: `bash tools/build.sh web-build`
2. `dist/` now holds `docker.tar.gz` (both images), `docker-compose.yml` and an empty `cookies.txt`.
3. Copy that folder to the target machine (which only needs Docker).
4. On the target, in that folder:
   1. `docker load -i docker.tar.gz`
   2. `mkdir downloads logs`
   3. `docker compose up -d`
5. Open `http://<target-host>:3000`.

### Use

1. Open **Settings**: upload `cookies.txt` and set the queue gap.
2. Open **Queue**: add rows (URL, audio/video, target folder) and queue them; playlists expand into per-track jobs.
3. **Retry Failed**, **Clear Completed** and **Clear All** work as in the desktop app; **History** keeps everything.
4. In **History**, **Clear History** deletes finished/failed entries.
5. Files appear in `./downloads`. Logs, uploaded cookies and the job database live inside the container only (not on the host) and survive container restarts, but are lost if the container is removed/recreated. Use the web app's **Logs** tab to browse log folders and view the latest entries in `.log` files.

### Run the web app without Docker

1. Backend (inside `.venv`): `uvicorn apps.api.main:app --host 0.0.0.0 --port 8000`
2. Frontend: `cd apps/web`, `npm install`, `npm run dev`

---

## Project layout

```text
music_pipeline/
├── core/            # shared queue/research engine (used by API and desktop)
├── apps/
│   ├── api/         # FastAPI service
│   ├── web/         # React UI
│   └── desktop/     # PySide6 app (ui.py + resources/desktop.ui, style.qss)
├── tools/           # setup.sh/.ps1 and build.sh/.ps1
├── docker-compose.yml
├── requirements.txt          # API + core packages
├── requirements-desktop.txt  # everything incl. PySide6 and PyInstaller
└── dist/            # build output (git-ignored)
```

## Troubleshooting

- **`Sign in to confirm you're not a bot`**: refresh `cookies.txt` and retry.
- **`Requested format is not available`**: make sure Deno is installed and on PATH (rerun the setup script).
- **`ffmpeg not found`**: rerun the setup script, then restart the terminal.
- **Metadata missing**: check `logs/` and that `mutagen` is installed.
- **`The Docker daemon is not running`**: start Docker Desktop and rerun the build.
