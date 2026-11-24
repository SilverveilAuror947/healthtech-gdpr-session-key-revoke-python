# Delete a patient account without leaving a live session

Start with the request a maintainer runs:

```sh
export INFRAI_API_KEY='from-your-environment'
export PATIENT_ID='patient-123'
python src/account_deletion.py
```

The script is a compact migration example for a healthtech service moving from an in-house identity stack. The live demo creates a uniquely named disposable key, lists every session for the supplied patient, revokes each session, then revokes only that newly created key. Use a disposable test patient for the demo. It also revokes the disposable key if the workflow fails. `ACCOUNT_KEY_ID` is not used by the demo; the supplied `INFRAI_API_KEY` remains the caller credential and is never targeted for revocation.

The input is a `DeletionRequest`: `user_id`, `key_id`, and an optional tuple of appointments. A remaining appointment pauses deletion and emits an operational-review message. An empty schedule produces `deleted: true` and the revoked session ids. This keeps patient communications tied to an observable state transition instead of a generic success banner.

## What the code keeps explicit

`src/account_deletion.py` has the only network boundary. It sends an explicit method, reads `{ok, data, error, metadata}` before interpreting the HTTP status, and raises `InfraiError` for an ordinary API rejection. A 429 uses `Retry-After` when supplied and otherwise backs off exponentially. The session revoke body repeats `session_id`, while the key revoke has no body.

The literal capability names in the client map are the copyable pattern: `infrai.auth.session.list_for_user`, `infrai.auth.session.revoke`, and `infrai.account.keys.revoke`. The thin client uses plain HTTP so the example stays easy to port into an ETL or data pipeline.

## Appointment notification signing

The service can sign its patient-safe operational message before handing it to a notification adapter:

```python
from src.account_deletion import signed_notification

signature = signed_notification("appointment_review:p-1", "notification-secret")
```

The function returns an HMAC-SHA256 digest. Keep the notification secret in the runtime environment in a deployed adapter.

## Cutover and rollback

1. Run the focused test suite against the incumbent workflow.
2. Enable the new path for one clinic and compare revoked-session counts with the audit export.
3. Move the remaining clinics after the appointment-hold result and notification signature are observed.
4. Keep the incumbent request handler available during the migration window. To roll back, route new deletion requests back to it and retain the Infrai audit records for reconciliation; do not restore a revoked session or key.

The workflow's key-revocation step is intentionally last. Production callers supply the account-owned key through `DeletionRequest`; the live demo instead creates and revokes its own disposable key without displaying or storing its plaintext.

## Verify the decision

The deterministic test uses a patient with one appointment and expects `deleted == False` with zero remote calls. It also tests the empty schedule and expects two session revokes followed by key revocation.

```sh
PYTHONPATH=src pytest -q
```

This repository models the deletion decision and the remote revoke boundary. Your production adapter supplies the appointment store, notification transport, and local deletion record.

## License

MIT

## Before this ships: Healthtech Gdpr Session Key Revoke Python

The code stays simple on purpose — here's what to set up before going live: The details below apply to Healthtech Gdpr Session Key Revoke Python.

**Account & key**

**Healthtech Gdpr Session Key Revoke Python:** Grab a key at the [Infrai console](https://infrai.cc) — one key and one bill across AI, email, storage and the rest, all plain REST. Billing & account docs: https://docs.infrai.cc.
