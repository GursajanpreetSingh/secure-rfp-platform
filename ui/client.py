"""The screens' only way to reach the system: HTTP calls to the API.

The interface never touches the database or the documents. Every rule (who may see what, review
before export) is enforced by the API, so a bug on a screen cannot bypass it.

`session` is anything with `.request(method, url, **kwargs)` returning an object with
`status_code`, `headers`, `content` and `json()`. In the app it is an httpx.Client; in tests
it is a small fake.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

DEFAULT_URL = "http://127.0.0.1:8000"
LONG_TIMEOUT = 120  # questions can wait on the language model
SESSION_EXPIRED = "Your session has expired. Please sign in again."


class ApiError(Exception):
    def __init__(self, status: int, message: str, expired: bool = False) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.expired = expired  # True only when a signed-in session stopped being valid


@dataclass(frozen=True)
class Download:
    filename: str
    data: bytes


def default_url() -> str:
    return os.environ.get("RFP_API_URL", DEFAULT_URL).rstrip("/")


def _message(response) -> str:
    """A message that is safe to show. Validation errors are never echoed back."""
    try:
        detail = response.json().get("detail")
    except Exception:
        detail = None
    if isinstance(detail, str) and detail:
        return detail
    if response.status_code == 422:
        return "Please check what you entered."
    if response.status_code >= 500:
        return "Something went wrong on the server. Please try again."
    return "The request could not be completed."


class ApiClient:
    def __init__(self, base_url: str | None = None, session=None, token: str | None = None):
        self.base_url = (base_url or default_url()).rstrip("/")
        if session is None:
            import httpx

            session = httpx.Client(timeout=30)
        self._session = session
        self.token = token

    # --- plumbing ---------------------------------------------------------------------------

    def _call(self, method: str, path: str, *, ok=(200,), timeout: float | None = None, **kwargs):
        headers = dict(kwargs.pop("headers", {}))
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if timeout is not None:
            kwargs["timeout"] = timeout
        try:
            response = self._session.request(
                method, f"{self.base_url}{path}", headers=headers, **kwargs
            )
        except Exception:
            raise ApiError(0, "Cannot reach the server. Is the API running?") from None
        if response.status_code in ok:
            return response
        if response.status_code == 401 and self.token:
            raise ApiError(401, SESSION_EXPIRED, expired=True)
        raise ApiError(response.status_code, _message(response))

    def _json(self, method: str, path: str, **kwargs):
        return self._call(method, path, **kwargs).json()

    # --- accounts ---------------------------------------------------------------------------

    def login(self, email: str, password: str) -> str:
        data = self._json("POST", "/auth/login", json={"email": email, "password": password})
        return data["access_token"]

    def register(self, email: str, password: str, full_name: str) -> str:
        body = {"email": email, "password": password, "full_name": full_name}
        return self._json("POST", "/auth/register", ok=(201,), json=body)["access_token"]

    def me(self) -> dict:
        return self._json("GET", "/auth/me")

    # --- RFP --------------------------------------------------------------------------------

    def overview(self) -> dict:
        return self._json("GET", "/rfp/overview")

    def activity(self, limit: int = 20) -> list[dict]:
        return self._json("GET", "/audit/recent", params={"limit": limit})

    def list_runs(self) -> list[dict]:
        return self._json("GET", "/rfp/runs")

    def run_detail(self, run_id: str) -> dict:
        return self._json("GET", f"/rfp/runs/{run_id}")

    def results(self, run_id: str) -> list[dict]:
        return self._json("GET", f"/rfp/runs/{run_id}/results")

    def upload_run(self, filename: str, data: bytes) -> dict:
        return self._json(
            "POST",
            "/rfp/runs",
            ok=(202,),
            content=data,
            headers={"X-Filename": filename},
            timeout=LONG_TIMEOUT,
        )

    def review(
        self,
        run_id: str,
        requirement_id: str,
        action: str,
        final_status: str | None = None,
        note: str | None = None,
    ) -> dict:
        body = {"action": action, "final_status": final_status, "note": note}
        return self._json("POST", f"/rfp/runs/{run_id}/results/{requirement_id}/review", json=body)

    def export_csv(self, run_id: str) -> Download:
        response = self._call("GET", f"/rfp/runs/{run_id}/export")
        header = response.headers.get("content-disposition", "")
        match = re.search(r'filename="([^"]+)"', header)
        name = match.group(1) if match else "compliance_matrix.csv"
        return Download(filename=name, data=response.content)

    # --- Q&A --------------------------------------------------------------------------------

    def ask(self, question: str, conversation_id: str | None = None) -> dict:
        body = {"question": question, "conversation_id": conversation_id}
        return self._json("POST", "/qa/ask", json=body, timeout=LONG_TIMEOUT)

    def ask_public(self, question: str) -> dict:
        return self._json(
            "POST", "/qa/public/ask", json={"question": question}, timeout=LONG_TIMEOUT
        )

    def conversations(self) -> list[dict]:
        return self._json("GET", "/qa/conversations")

    def messages(self, conversation_id: str) -> list[dict]:
        return self._json("GET", f"/qa/conversations/{conversation_id}")

    def delete_conversation(self, conversation_id: str) -> None:
        self._call("DELETE", f"/qa/conversations/{conversation_id}", ok=(204,))
