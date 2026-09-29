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
REQUEST_TIMEOUT_SECONDS = 8


class UpdateError(Exception):
    pass


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
                    chunk = response.read(1024 * 256)
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
            self.state.update(status="downloading", message="Preparing secure download…")

        def worker():
            try:
                self.staging_dir = _download_and_stage(
                    self.release,
                    self.install_dir,
                    self._on_progress,
                    self.cancelled,
                )
                self._set_state(status="ready", message="Verified. Installing update…", percent=100)
            except Exception as error:
                if self.cancelled.is_set():
                    self._set_state(status="cancelled", message="Download cancelled.")
                else:
                    self._set_state(status="error", message=str(error))

        threading.Thread(target=worker, daemon=True).start()
        return {"status": "downloading"}

    def _on_progress(self, downloaded, total):
        percent = min(99, int(downloaded * 100 / total)) if total else 0
        message = (
            f"Downloading update… {percent}%"
            if total
            else f"Downloaded {downloaded // (1024 * 1024)} MB…"
        )
        self._set_state(message=message, percent=percent)

    def cancel_update(self):
        self.cancelled.set()
        return {"status": "cancelling"}

    def on_window_closing(self):
        self.cancelled.set()

    def continue_to_app(self):
        if self.cancelled.is_set() and self.staging_dir:
            shutil.rmtree(self.staging_dir, ignore_errors=True)
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
                self._set_state(status="handed_off", message="Restarting with the new version…")
                self.window.destroy()
            except Exception as error:
                if self.staging_dir:
                    shutil.rmtree(self.staging_dir, ignore_errors=True)
                self.handoff_started = False
                self._set_state(status="error", message=str(error))

        with self.lock:
            return self.state.copy()


def make_update_prompt(release, main_url):
    """Return the HTML prompt and Python API for the packaged WebView window."""
    if not getattr(sys, "frozen", False):
        return None, None

    install_dir = os.path.dirname(sys.executable)
    if not os.path.isfile(os.path.join(install_dir, UPDATER_EXECUTABLE)):
        return None, None

    api = UpdatePromptApi(release, install_dir, sys.executable, main_url)
    notes = release["notes"] or "Performance improvements and bug fixes."
    # JSON encoding makes release notes safe to place in the page as text.
    notes_json = (
        json.dumps(notes[:500], ensure_ascii=True)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
    version_json = json.dumps(release["version"])
    html = f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{{box-sizing:border-box}} body{{margin:0;background:#f4f7fb;color:#132238;font-family:'Segoe UI',Arial,sans-serif}}
main{{padding:25px 29px 22px}} .eyebrow{{color:#54708f;font-size:10px;font-weight:700;letter-spacing:1.4px}}
h1{{font-size:23px;line-height:1.2;margin:9px 0 5px}} .sub{{color:#52647a;font-size:13px}}
.card{{margin-top:18px;padding:14px 16px;background:white;border:1px solid #e2e9f2;border-radius:12px;height:126px;overflow:auto}}
.card strong{{font-size:12px}} .notes{{margin-top:8px;color:#52647a;font-size:12px;line-height:1.5;white-space:pre-wrap}}
.status{{margin:15px 0 8px;color:#52647a;font-size:11px;min-height:16px}}
.track{{height:7px;background:#e2e9f2;border-radius:99px;overflow:hidden}} .fill{{width:0;height:100%;background:#2878d0;border-radius:99px;transition:width .2s}}
.buttons{{display:flex;justify-content:flex-end;gap:9px;margin-top:17px}}
button{{border:0;border-radius:8px;padding:10px 18px;font:600 12px 'Segoe UI',Arial;cursor:pointer}}
.primary{{background:#1769c2;color:white}} .primary:hover{{background:#1257a3}}
.secondary{{background:#e8edf4;color:#26384e}} button:disabled{{opacity:.55;cursor:default}}
.fill.preparing{{width:35%;animation:slide 1.1s ease-in-out infinite alternate}}
@keyframes slide{{from{{transform:translateX(-55%)}}to{{transform:translateX(190%)}}}}
</style></head><body><main>
<div class="eyebrow">OPERON &nbsp;/&nbsp; SOFTWARE UPDATE</div>
<h1>A new version is ready</h1>
<div class="sub">HR Management System &nbsp;·&nbsp; Version <span id="version"></span></div>
<section class="card"><strong>What’s new</strong><div class="notes" id="notes"></div></section>
<div class="status" id="status">Would you like to install this update now?</div>
<div class="track"><div class="fill" id="fill"></div></div>
<div class="buttons"><button class="secondary" id="later" onclick="continueApp()" disabled>Later</button>
<button class="primary" id="update" onclick="startUpdate()" disabled>Update now</button></div>
</main><script>
const releaseVersion={version_json}, releaseNotes={notes_json};
document.getElementById('version').textContent=releaseVersion;
document.getElementById('notes').textContent=releaseNotes;
let pollTimer=null, apiReady=false;
const updateButton=document.getElementById('update');
const laterButton=document.getElementById('later');
const statusLabel=document.getElementById('status');
const progressFill=document.getElementById('fill');
function markApiReady(){{
 apiReady=true; updateButton.disabled=false; laterButton.disabled=false;
 statusLabel.textContent='Would you like to install this update now?';
}}
if(window.pywebview && window.pywebview.api) markApiReady();
else window.addEventListener('pywebviewready',markApiReady,{{once:true}});
function showApiError(error){{
 if(pollTimer) clearInterval(pollTimer); pollTimer=null;
 progressFill.classList.remove('preparing'); progressFill.style.width='0%';
 statusLabel.textContent='The updater could not start: '+(error && error.message ? error.message : String(error));
 updateButton.disabled=false; updateButton.textContent='Try again';
 laterButton.disabled=false; laterButton.textContent='Open app'; laterButton.onclick=continueApp;
}}
async function startUpdate(){{
 if(!apiReady) return;
 updateButton.disabled=true; laterButton.textContent='Cancel';
 laterButton.onclick=cancelUpdate; statusLabel.textContent='Connecting to GitHub…';
 progressFill.classList.add('preparing');
 try{{
  await window.pywebview.api.start_update();
  progressFill.classList.remove('preparing');
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
 progressFill.style.width=(s.percent||0)+'%';
 if(s.status==='error'||s.status==='cancelled'){{
  clearInterval(pollTimer); pollTimer=null;
  updateButton.disabled=false;
  updateButton.textContent=s.status==='error'?'Try again':'Update now';
  laterButton.disabled=false; laterButton.textContent='Open app';
  laterButton.onclick=continueApp;
 }}
}}
</script></body></html>"""
    return html, api
