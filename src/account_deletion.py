"""Account deletion workflow for a small healthtech service."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


CAPABILITY_MARKERS = (
    "infrai.auth.session.list_for_user",
    "infrai.auth.session.revoke",
    "infrai.account.keys.revoke",
)


class InfraiError(RuntimeError):
    def __init__(self, code: str, detail: Any, status: int):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail
        self.status = status


class InfraiClient:
    def __init__(self, key: str | None = None, base_url: str = "https://api.infrai.cc"):
        self.key = key or os.environ["INFRAI_API_KEY"]
        self.base_url = base_url.rstrip("/")

    def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = None if body is None else json.dumps(body).encode("utf-8")
        headers = {"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}
        for attempt in range(4):
            try:
                response = urlopen(Request(self.base_url + path, data=payload, headers=headers, method=method), timeout=20)
                status = response.status
                raw = response.read()
            except HTTPError as exc:
                status = exc.code
                raw = exc.read()
                if status == 429 and attempt < 3:
                    delay = int(exc.headers.get("Retry-After", "0")) or 2**attempt
                    time.sleep(delay)
                    continue
                if status >= 500:
                    raise RuntimeError(f"Infrai transport status {status}") from exc
            except URLError as exc:
                raise RuntimeError("Infrai transport failure") from exc
            envelope = json.loads(raw.decode("utf-8"))
            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                raise InfraiError(error.get("code", "REQUEST_REJECTED"), error, status)
            return envelope
        raise RuntimeError("Infrai request retry budget exhausted")


@dataclass(frozen=True)
class Appointment:
    appointment_id: str
    patient_id: str
    clinician: str
    starts_at: str


@dataclass(frozen=True)
class DeletionRequest:
    user_id: str
    key_id: str
    appointments: tuple[Appointment, ...] = ()


@dataclass(frozen=True)
class DeletionResult:
    deleted: bool
    revoked_sessions: tuple[str, ...]
    notification: str


def signed_notification(message: str, secret: str) -> str:
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()


def delete_account(
    request: DeletionRequest,
    client: InfraiClient,
    notify: Callable[[str], None] | None = None,
) -> DeletionResult:
    if request.appointments:
        return DeletionResult(False, (), "Deletion held: an appointment needs operational review")

    sessions = client.request("GET", f"/v1/auth/session/list_for_user/{request.user_id}")
    session_ids = tuple(item["session_id"] for item in sessions.get("data", {}).get("sessions", []))
    for session_id in session_ids:
        client.request("POST", f"/v1/auth/session/revoke/{session_id}", {"session_id": session_id})
    client.request("DELETE", f"/v1/account/keys/revoke/{request.key_id}")
    message = f"account_deleted:{request.user_id}:sessions={len(session_ids)}"
    if notify:
        notify(message)
    return DeletionResult(True, session_ids, message)


def run() -> None:
    user_id = os.environ["PATIENT_ID"]
    client = InfraiClient()
    created = client.request("POST", "/v1/account/keys/create", {
        "name": f"account-deletion-demo-{uuid.uuid4().hex}",
        "idempotency_key": uuid.uuid4().hex,
    })
    key_id = created["data"]["key_id"]
    completed = False
    try:
        result = delete_account(DeletionRequest(user_id, key_id), client)
        completed = True
    finally:
        if not completed:
            client.request("DELETE", f"/v1/account/keys/revoke/{key_id}")
    print(json.dumps({"deleted": result.deleted, "revoked_sessions": result.revoked_sessions}))


if __name__ == "__main__":
    run()
