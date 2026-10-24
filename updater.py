"""GitHub Releases update check and Windows update prompt."""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request
import zipfile

from app_version import APP_VERSION


GITHUB_OWNER = "simarCoder"
GITHUB_REPOSITORY = "employee-attendance-system"
RELEASE_API = (
    f"https://api.github.com/repos/{GITHUB_OWNER}/"
    f"{GITHUB_REPOSITORY}/releases/latest"
)
PACKAGE_ASSET = "HR_Management_System-win64.zip"
APP_EXECUTABLE = "HR_Management_System.exe"
UPDATER_EXECUTABLE = "HR_Management_System_Updater.exe"
REQUEST_TIMEOUT_SECONDS = 30


class UpdateError(Exception):
    pass


def clean_release_notes(raw_notes):
    """
    Sanitize GitHub release notes to remove technical links, commit hashes,
    and GitHub repository references, leaving only clean bullet points for clients.
    """
    if not raw_notes or not raw_notes.strip():
        return "• Performance optimizations and stability improvements.\n• Bug fixes and payroll updates."

    cleaned_lines = []
    for line in raw_notes.splitlines():
        line = line.strip()
        if not line:
            continue
        # Remove GitHub headers and technical lines
        if line.startswith("## What's Changed") or line.startswith("# What's Changed") or line.startswith("## Release"):
            continue
        if "full changelog" in line.lower():
            continue
        if "github.com" in line or "http://" in line or "https://" in line:
            line = re.sub(r"\s+in\s+https?://\S+", "", line)
            line = re.sub(r"\s+by\s+@\S+", "", line)
            line = re.sub(r"https?://\S+", "", line).strip()
            if not line or line in ("*", "-", "•"):
                continue

        # Clean bullet formatting
        if line.startswith("* ") or line.startswith("- "):
            line = "• " + line[2:].strip()
        elif not line.startswith("• ") and not line.startswith("v") and not line.endswith(":"):
            line = "• " + line

        cleaned_lines.append(line)

    if not cleaned_lines:
        return "• Performance optimizations and stability improvements.\n• Bug fixes and payroll updates."

    return "\n".join(cleaned_lines)


def _version_tuple(value):
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", str(value).strip())
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


def _github_request(url):
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Operon-HR-Management-System-Updater",
        },
    )
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        return response.read()


def get_available_release():
    try:
        release = json.loads(_github_request(RELEASE_API).decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError, UnicodeDecodeError):
        return None

    current = _version_tuple(APP_VERSION)
    latest = _version_tuple(release.get("tag_name", ""))
    if not current or not latest or latest <= current:
        return None

    asset = next(
        (item for item in release.get("assets", []) if item.get("name") == PACKAGE_ASSET),
        None,
    )
    if not asset or not asset.get("browser_download_url"):
        return None

    digest = asset.get("digest", "")
    if not digest.startswith("sha256:"):
        return None

    return {
        "version": release["tag_name"].lstrip("v"),
        "download_url": asset["browser_download_url"],
        "sha256": digest.split(":", 1)[1].lower(),
        "notes": (release.get("body") or "").strip(),
    }


def _download_and_stage(release, install_dir, progress, cancelled):
    staging_dir = tempfile.mkdtemp(prefix=".hrms-update-", dir=install_dir)
    archive_path = os.path.join(staging_dir, PACKAGE_ASSET)
    try:
        request = urllib.request.Request(
            release["download_url"],
            headers={"User-Agent": "Operon-HR-Management-System-Updater"},
        )
        digest = hashlib.sha256()
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            total = int(response.headers.get("Content-Length", "0") or 0)
            downloaded = 0
            with open(archive_path, "wb") as output:
                while True:
                    if cancelled.is_set():
                        raise UpdateError("Update cancelled")
                    chunk = response.read(1024 * 512)
                    if not chunk:
                        break
                    output.write(chunk)
                    digest.update(chunk)
                    downloaded += len(chunk)
                    progress(downloaded, total)

        if cancelled.is_set():
            raise UpdateError("Update cancelled")
        if digest.hexdigest() != release["sha256"]:
            raise UpdateError("The downloaded package failed its SHA-256 check.")

        with zipfile.ZipFile(archive_path) as package:
            names = set(package.namelist())
            expected = {APP_EXECUTABLE, UPDATER_EXECUTABLE}
            if not expected.issubset(names):
                raise UpdateError("The release package is missing required application files.")
            for filename in expected:
                info = package.getinfo(filename)
                if info.is_dir() or os.path.basename(info.filename) != info.filename:
                    raise UpdateError("The release package contains an invalid file path.")
                with package.open(info) as source, open(
                    os.path.join(staging_dir, filename), "wb"
                ) as target:
                    shutil.copyfileobj(source, target)

        if cancelled.is_set():
            raise UpdateError("Update cancelled")
        os.remove(archive_path)
        return staging_dir
    except Exception:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise


class UpdatePromptApi:
    """WebView bridge for the update prompt and its download progress."""

    def __init__(self, release, install_dir, current_executable, main_url):
        self.release = release
        self.install_dir = install_dir
        self.current_executable = current_executable
        self.main_url = main_url
        self.window = None
        self.cancelled = threading.Event()
        self.lock = threading.Lock()
        self.state = {
            "status": "prompt",
            "message": "Would you like to install this update now?",
            "percent": 0,
            "indeterminate": False,
        }
        self.staging_dir = None
        self.handed_off = False
        self.handoff_started = False

    def _set_state(self, **values):
        with self.lock:
            self.state.update(values)

    def start_update(self):
        with self.lock:
            if self.state["status"] not in {"prompt", "error", "cancelled"}:
                return self.state.copy()
            self.cancelled = threading.Event()
            self.staging_dir = None
            self.state.update(
                status="downloading",
                message="Preparing secure download…",
                percent=0,
                indeterminate=True,
            )

        def worker():
            try:
                self.staging_dir = _download_and_stage(
                    self.release,
                    self.install_dir,
                    self._on_progress,
                    self.cancelled,
                )
                self._set_state(
                    status="ready",
                    message="Download verified. Preparing installation…",
                    percent=100,
                    indeterminate=False,
                )
            except Exception as error:
                if self.cancelled.is_set():
                    self._set_state(status="cancelled", message="Download cancelled.")
                else:
                    self._set_state(status="error", message=str(error))

        threading.Thread(target=worker, daemon=True).start()
        return {"status": "downloading"}

    def _on_progress(self, downloaded, total):
        percent = min(99, int(downloaded * 100 / total)) if total else 0
        if total:
            dl_mb = downloaded / (1024 * 1024)
            tot_mb = total / (1024 * 1024)
            message = f"Downloading update… {dl_mb:.1f} MB / {tot_mb:.1f} MB ({percent}%)"
        else:
            dl_mb = downloaded / (1024 * 1024)
            message = f"Downloading update… {dl_mb:.1f} MB"
        self._set_state(
            message=message,
            percent=percent,
            indeterminate=not bool(total),
        )

    def cancel_update(self):
        self.cancelled.set()
        return {"status": "cancelling"}

    def on_window_closing(self):
        if not self.handoff_started and not self.handed_off:
            self.cancelled.set()

    def continue_to_app(self):
        if self.cancelled.is_set() and self.staging_dir:
            threading.Thread(
                target=shutil.rmtree,
                args=(self.staging_dir,),
                kwargs={"ignore_errors": True},
                daemon=True,
            ).start()
        self.window.load_url(self.main_url)
        self.window.resize(1400, 900)
        self.window.maximize()
        return True

    def get_state(self):
        with self.lock:
            state = self.state.copy()
            should_handoff = state["status"] == "ready" and not self.handoff_started
            if should_handoff:
                self.handoff_started = True

        if should_handoff:
            # Keep filesystem work and process launch off the WebView bridge
            # thread so polling the state can never stall the dialog.
            threading.Thread(target=self._handoff_update, daemon=True).start()

        with self.lock:
            return self.state.copy()

    def _handoff_update(self):
        try:
            helper = os.path.join(self.install_dir, UPDATER_EXECUTABLE)
            runner = os.path.join(
                tempfile.gettempdir(), f"hrms-updater-{os.getpid()}.exe"
            )
            shutil.copy2(helper, runner)
            subprocess.Popen(
                [
                    runner,
                    "--parent-pid",
                    str(os.getpid()),
                    "--install-dir",
                    self.install_dir,
                    "--staging-dir",
                    self.staging_dir,
                    "--app-executable",
                    os.path.basename(self.current_executable),
                    "--helper-executable",
                    UPDATER_EXECUTABLE,
                ],
                close_fds=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            self.handed_off = True
            self._set_state(
                status="handed_off",
                message="Restarting with the new version…",
            )
            if self.window:
                self.window.destroy()
        except Exception as error:
            if self.staging_dir:
                shutil.rmtree(self.staging_dir, ignore_errors=True)
            self.handoff_started = False
            self._set_state(status="error", message=str(error))


def make_update_prompt(release, main_url):
    """Return the HTML prompt and Python API for the packaged WebView window."""
    if not getattr(sys, "frozen", False):
        return None, None

    install_dir = os.path.dirname(sys.executable)
    if not os.path.isfile(os.path.join(install_dir, UPDATER_EXECUTABLE)):
        return None, None

    api = UpdatePromptApi(release, install_dir, sys.executable, main_url)
    raw_notes = release.get("notes") or ""
    notes = clean_release_notes(raw_notes)
    # JSON encoding makes release notes safe to place in the page as text.
    notes_json = (
        json.dumps(notes[:800], ensure_ascii=True)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
    version_json = json.dumps(release["version"])
    html = f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
html {{ background: #000000; height: 100%; }}
body {{
  margin: 0;
  background: #000000;
  color: #f5f5f5;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
  height: 100%;
  overflow: hidden;
  user-select: none;
  opacity: 0;
  transition: opacity 0.18s ease;
}}
html.ready body {{ opacity: 1; }}

main {{
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 22px 26px 20px;
}}

.header {{
  margin-bottom: 12px;
}}

.pill-badge {{
  display: inline-flex;
  align-items: center;
  background: rgba(56, 189, 248, 0.12);
  border: 1px solid rgba(56, 189, 248, 0.28);
  color: #38bdf8;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  padding: 3px 9px;
  border-radius: 99px;
  margin-bottom: 8px;
}}

h1 {{
  font-size: 20px;
  font-weight: 700;
  color: #ffffff;
  letter-spacing: -0.01em;
  margin-bottom: 4px;
}}

.sub {{
  color: #888888;
  font-size: 12px;
  font-weight: 500;
}}

.sub strong {{
  color: #e5e5e5;
  font-weight: 600;
}}

.card {{
  flex: 1;
  background: #080808;
  border: 1px solid #222222;
  border-radius: 10px;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  margin-bottom: 12px;
}}

.card-title {{
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: #a3a3a3;
  margin-bottom: 7px;
}}

.notes {{
  flex: 1;
  overflow-y: auto;
  color: #d4d4d4;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  padding-right: 4px;
}}

.notes::-webkit-scrollbar {{
  width: 5px;
}}
.notes::-webkit-scrollbar-track {{
  background: transparent;
}}
.notes::-webkit-scrollbar-thumb {{
  background: #262626;
  border-radius: 4px;
}}
.notes::-webkit-scrollbar-thumb:hover {{
  background: #383838;
}}

.status {{
  font-size: 11px;
  font-weight: 500;
  color: #999999;
  margin-bottom: 8px;
  min-height: 16px;
}}

.track {{
  height: 6px;
  background: #141414;
  border: 1px solid #222222;
  border-radius: 99px;
  overflow: hidden;
  margin-bottom: 14px;
}}

.fill {{
  width: 0%;
  height: 100%;
  background: #38bdf8;
  border-radius: 99px;
  transition: width 0.2s cubic-bezier(0.16, 1, 0.3, 1);
}}

.fill.indeterminate {{
  width: 35%;
  animation: slide 1.1s cubic-bezier(0.4, 0, 0.2, 1) infinite alternate;
}}

@keyframes slide {{
  from {{ transform: translateX(-50%); }}
  to {{ transform: translateX(200%); }}
}}

.buttons {{
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}}

button {{
  border: 1px solid transparent;
  border-radius: 7px;
  padding: 8px 18px;
  font-family: inherit;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.18s cubic-bezier(0.16, 1, 0.3, 1);
}}

button:active {{
  transform: scale(0.96);
}}

.primary {{
  background: #0284c7;
  color: #ffffff;
  border-color: #0369a1;
  box-shadow: 0 1px 6px rgba(2, 132, 199, 0.35);
}}

.primary:hover {{
  background: #0369a1;
  border-color: #075985;
}}

.secondary {{
  background: #121212;
  color: #a3a3a3;
  border-color: #262626;
}}

.secondary:hover {{
  background: #1c1c1c;
  color: #ffffff;
  border-color: #383838;
}}

button:disabled {{
  opacity: 0.45;
  cursor: default;
  transform: none !important;
}}
</style>
</head>
<body>
<main>
  <div class="header">
    <div class="pill-badge">Operon &middot; Update Available</div>
    <h1>A new version is ready</h1>
    <div class="sub">HR Management System &nbsp;&middot;&nbsp; Version <strong id="version"></strong></div>
  </div>

  <section class="card">
    <div class="card-title">What's New in this Version</div>
    <div class="notes" id="notes"></div>
  </section>

  <div class="status" id="status">Would you like to install this update now?</div>
  <div class="track"><div class="fill" id="fill"></div></div>

  <div class="buttons">
    <button class="secondary" id="later" onclick="continueApp()" disabled>Later</button>
    <button class="primary" id="update" onclick="startUpdate()" disabled>Update now</button>
  </div>
</main>
<script>
const releaseVersion={version_json}, releaseNotes={notes_json};
document.getElementById('version').textContent=releaseVersion;
document.getElementById('notes').textContent=releaseNotes;
let pollTimer=null, apiReady=false, uiReady=false, updateStarted=false;
const updateButton=document.getElementById('update');
const laterButton=document.getElementById('later');
const statusLabel=document.getElementById('status');
const progressFill=document.getElementById('fill');
function unlockWhenReady(){{
 if(!apiReady||!uiReady) return;
 updateButton.disabled=false; laterButton.disabled=false;
 statusLabel.textContent='Would you like to install this update now?';
}}
function markApiReady(){{apiReady=true;unlockWhenReady();}}
window.addEventListener('load',()=>requestAnimationFrame(()=>requestAnimationFrame(()=>{{
 uiReady=true; document.documentElement.classList.add('ready'); unlockWhenReady();
}})),{{once:true}});
if(window.pywebview && window.pywebview.api) markApiReady();
else window.addEventListener('pywebviewready',markApiReady,{{once:true}});
function showApiError(error){{
 if(pollTimer) clearInterval(pollTimer); pollTimer=null;
 updateStarted=false; progressFill.classList.remove('indeterminate'); progressFill.style.width='0%';
 statusLabel.textContent='The updater could not start: '+(error && error.message ? error.message : String(error));
 updateButton.disabled=false; updateButton.textContent='Try again';
 laterButton.disabled=false; laterButton.textContent='Open app'; laterButton.onclick=continueApp;
}}
async function startUpdate(){{
 if(!apiReady||!uiReady||updateStarted) return;
 updateStarted=true; updateButton.disabled=true; laterButton.textContent='Cancel';
 laterButton.onclick=cancelUpdate; laterButton.disabled=false; statusLabel.textContent='Starting download…';
 progressFill.style.width='0%'; progressFill.classList.add('indeterminate');
 try{{
  await window.pywebview.api.start_update();
  pollTimer=setInterval(pollState,300); pollState();
 }}catch(error){{showApiError(error);}}
}}
async function cancelUpdate(){{
 if(!apiReady) return;
 statusLabel.textContent='Cancelling download…';
 try{{await window.pywebview.api.cancel_update();}}
 catch(error){{showApiError(error);return;}}
 laterButton.textContent='Open app'; laterButton.onclick=continueApp;
}}
async function continueApp(){{
 if(!apiReady) return;
 if(pollTimer) clearInterval(pollTimer);
 try{{await window.pywebview.api.continue_to_app();}}
 catch(error){{showApiError(error);}}
}}
async function pollState(){{
 let s;
 try{{s=await window.pywebview.api.get_state();}}
 catch(error){{showApiError(error);return;}}
 statusLabel.textContent=s.message;
 progressFill.classList.toggle('indeterminate',!!s.indeterminate);
 if(!s.indeterminate) progressFill.style.width=(s.percent||0)+'%';
 if(s.status==='ready'){{updateButton.disabled=true;laterButton.disabled=true;}}
 if(s.status==='handed_off'){{clearInterval(pollTimer);pollTimer=null;}}
 if(s.status==='error'||s.status==='cancelled'){{
  clearInterval(pollTimer); pollTimer=null;
  updateStarted=false; progressFill.classList.remove('indeterminate');
  updateButton.disabled=false;
  updateButton.textContent=s.status==='error'?'Try again':'Update now';
  laterButton.disabled=false; laterButton.textContent='Open app';
  laterButton.onclick=continueApp;
 }}
}}
</script></body></html>"""
    return html, api
