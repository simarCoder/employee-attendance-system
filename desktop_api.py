"""Desktop-only operations exposed to the PyWebView frontend."""

import json
import re
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

import webview


class DesktopApi:
    def __init__(self, base_url):
        self.base_url = base_url.rstrip("/")
        self.window = None

    def save_salary_pdf(self, month, employee_id=None):
        """Fetch a generated payroll PDF and save it through a native dialog."""
        if not isinstance(month, str) or not re.fullmatch(
            r"\d{4}-(0[1-9]|1[0-2])", month
        ):
            raise ValueError("Choose a valid payroll month.")

        params = {"month": month}
        if employee_id is not None:
            try:
                employee_id = int(employee_id)
            except (TypeError, ValueError):
                raise ValueError("Choose a valid employee.")
            if employee_id <= 0:
                raise ValueError("Choose a valid employee.")
            params["employee_id"] = employee_id

        filename = (
            f"salary-statement-{employee_id}-{month}.pdf"
            if employee_id is not None
            else f"payroll-register-{month}.pdf"
        )
        url = f"{self.base_url}/salary/pdf?{urlencode(params)}"

        try:
            with urlopen(url, timeout=60) as response:
                pdf_bytes = response.read()
        except HTTPError as exc:
            try:
                detail = json.loads(exc.read().decode("utf-8"))
                message = detail.get( "error") or detail.get("message")
            except (UnicodeDecodeError, json.JSONDecodeError):
                message = None
            raise RuntimeError(message or "The PDF could not be generated.")
        except URLError:
            raise RuntimeError("The payroll service is unavailable. Please retry.")

        if not pdf_bytes.startswith(b"%PDF-"):
            raise RuntimeError("The payroll service returned an invalid PDF.")
        if self.window is None:
            raise RuntimeError("The desktop save dialog is not ready.")

        file_dialog = getattr(webview, "FileDialog", None)
        save_dialog = getattr(file_dialog, "SAVE", None)
        if save_dialog is None:
            save_dialog = webview.SAVE_DIALOG

        selected = self.window.create_file_dialog(
            save_dialog,
            save_filename=filename,
            file_types=("PDF files (*.pdf)",),
        )
        if not selected:
            return {"saved": False, "cancelled": True}

        destination = Path(selected[0])
        if destination.suffix.lower() != ".pdf":
            destination = destination.with_suffix(".pdf")
        destination.write_bytes(pdf_bytes)

        return {"saved": True, "path": str(destination)}
