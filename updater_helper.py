"""Small Windows helper that replaces a running one-file application safely."""

import argparse
import ctypes
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime


WAIT_OBJECT_0 = 0
SYNCHRONIZE = 0x00100000


def _wait_for_process_exit(pid, timeout_seconds=120):
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
    if not handle:
        return True
    try:
        result = kernel32.WaitForSingleObject(handle, timeout_seconds * 1000)
        return result == WAIT_OBJECT_0
    finally:
        kernel32.CloseHandle(handle)


def _backup_name(path, stamp):
    return os.path.join("old_files", f"{os.path.basename(path)}.{stamp}.bak")


def apply_update(args):
    install_dir = os.path.abspath(args.install_dir)
    staging_dir = os.path.abspath(args.staging_dir)
    app_path = os.path.join(install_dir, args.app_executable)
    staged_app = os.path.join(staging_dir, args.app_executable)
    helper_name = args.helper_executable
    installed_helper = os.path.join(install_dir, helper_name)
    staged_helper = os.path.join(staging_dir, helper_name)

    if not _wait_for_process_exit(args.parent_pid):
        raise RuntimeError("The application did not close in time; update cancelled.")

    if not os.path.isfile(staged_app) or not os.path.isfile(staged_helper):
        raise RuntimeError("Staged update files are incomplete.")

    old_files = os.path.join(install_dir, "old_files")
    os.makedirs(old_files, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    app_backup = os.path.join(install_dir, _backup_name(app_path, stamp))
    helper_backup = os.path.join(install_dir, _backup_name(installed_helper, stamp))
    app_backed_up = False
    helper_backed_up = False
    app_installed = False
    helper_installed = False

    try:
        os.replace(app_path, app_backup)
        app_backed_up = True
        if os.path.isfile(installed_helper):
            os.replace(installed_helper, helper_backup)
            helper_backed_up = True
        os.replace(staged_app, app_path)
        app_installed = True
        os.replace(staged_helper, installed_helper)
        helper_installed = True
    except Exception:
        if app_installed and os.path.exists(app_path):
            os.remove(app_path)
        if helper_installed and os.path.exists(installed_helper):
            os.remove(installed_helper)
        if app_backed_up and os.path.exists(app_backup):
            os.replace(app_backup, app_path)
        if helper_backed_up and os.path.exists(helper_backup):
            os.replace(helper_backup, installed_helper)
        raise
    finally:
        shutil.rmtree(staging_dir, ignore_errors=True)

    subprocess.Popen([app_path], cwd=install_dir, close_fds=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent-pid", required=True, type=int)
    parser.add_argument("--install-dir", required=True)
    parser.add_argument("--staging-dir", required=True)
    parser.add_argument("--app-executable", required=True)
    parser.add_argument("--helper-executable", required=True)
    args = parser.parse_args()
    try:
        apply_update(args)
    except Exception as error:
        log_path = os.path.join(args.install_dir, "update-error.log")
        try:
            with open(log_path, "a", encoding="utf-8") as log:
                log.write(f"{datetime.now().isoformat()} Update failed: {error}\n")
        except OSError:
            pass
        app_path = os.path.join(os.path.abspath(args.install_dir), args.app_executable)
        if os.path.isfile(app_path):
            try:
                subprocess.Popen([app_path], cwd=args.install_dir, close_fds=True)
            except OSError:
                pass
        time.sleep(1)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
