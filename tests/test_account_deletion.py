from account_deletion import Appointment, DeletionRequest, DeletionResult, delete_account


class FakeClient:
    def __init__(self):
        self.calls = []

    def request(self, method, path, body=None):
        self.calls.append((method, path, body))
        if path.startswith("/v1/auth/session/list_for_user/"):
            return {"ok": True, "data": {"sessions": [{"session_id": "s-1"}, {"session_id": "s-2"}]}}
        return {"ok": True, "data": {}}


def test_appointment_holds_deletion_before_any_remote_change():
    client = FakeClient()
    appointment = Appointment("a-1", "p-1", "Dr Chen", "2030-04-05T09:00:00Z")

    result = delete_account(DeletionRequest("p-1", "key-1", (appointment,)), client)

    assert result == DeletionResult(False, (), "Deletion held: an appointment needs operational review")
    assert client.calls == []


def test_empty_schedule_revokes_sessions_then_account_key():
    client = FakeClient()

    result = delete_account(DeletionRequest("p-1", "key-1"), client)

    assert result.deleted is True
    assert result.revoked_sessions == ("s-1", "s-2")
    assert client.calls == [
        ("GET", "/v1/auth/session/list_for_user/p-1", None),
        ("POST", "/v1/auth/session/revoke/s-1", {"session_id": "s-1"}),
        ("POST", "/v1/auth/session/revoke/s-2", {"session_id": "s-2"}),
        ("DELETE", "/v1/account/keys/revoke/key-1", None),
    ]


def test_demo_ignores_external_key_and_cleans_up_on_failure(monkeypatch):
    import src.account_deletion as demo
    import pytest

    class DemoClient(FakeClient):
        def request(self, method, path, body=None):
            self.calls.append((method, path, body))
            if path == '/v1/account/keys/create':
                return {'data': {'key_id': 'new-disposable-key'}}
            if path.startswith('/v1/auth/session/list_for_user/'):
                raise ValueError('workflow failed')
            return {'data': {'revoked': True}}

    client = DemoClient()
    monkeypatch.setenv('PATIENT_ID', 'test-patient')
    monkeypatch.setenv('ACCOUNT_KEY_ID', 'pre-existing-key')
    monkeypatch.setattr(demo, 'InfraiClient', lambda: client)
    with pytest.raises(ValueError, match='workflow failed'):
        demo.run()
    assert client.calls[-1] == ('DELETE', '/v1/account/keys/revoke/new-disposable-key', None)
    assert all('pre-existing-key' not in path for _, path, _ in client.calls)
