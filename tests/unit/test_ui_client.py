import pytest

from ui.client import SESSION_EXPIRED, ApiClient, ApiError


class FakeResponse:
    def __init__(self, status=200, body=None, headers=None, content=b""):
        self.status_code = status
        self._body = body
        self.headers = headers or {}
        self.content = content

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


class FakeSession:
    def __init__(self, *responses, fail=False):
        self.responses, self.calls, self.fail = list(responses), [], fail

    def request(self, method, url, **kwargs):
        if self.fail:
            raise OSError("connection refused")
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)


def client(*responses, token=None, **kwargs):
    session = FakeSession(*responses, **kwargs)
    return ApiClient("http://api.test/", session=session, token=token), session


def test_login_posts_the_credentials_and_returns_the_token():
    api, session = client(FakeResponse(200, {"access_token": "T1"}))
    assert api.login("a@b.co", "pw") == "T1"
    method, url, kwargs = session.calls[0]
    assert (method, url) == ("POST", "http://api.test/auth/login")
    assert kwargs["json"] == {"email": "a@b.co", "password": "pw"}
    assert "Authorization" not in kwargs["headers"]


def test_register_expects_201_and_sends_no_role():
    api, session = client(FakeResponse(201, {"access_token": "T2"}))
    assert api.register("a@b.co", "long enough pw", "Asha") == "T2"
    assert set(session.calls[0][2]["json"]) == {"email", "password", "full_name"}


def test_the_token_is_sent_on_later_calls():
    api, session = client(FakeResponse(200, {"email": "x"}), token="T3")
    api.me()
    assert session.calls[0][2]["headers"]["Authorization"] == "Bearer T3"


def test_a_wrong_login_shows_the_servers_message_not_a_session_expiry():
    api, _ = client(FakeResponse(401, {"detail": "invalid email or password"}))
    with pytest.raises(ApiError) as error:
        api.login("a@b.co", "bad")
    assert error.value.message == "invalid email or password"
    assert error.value.expired is False


def test_a_401_while_signed_in_means_the_session_expired():
    api, _ = client(FakeResponse(401, {"detail": "x"}), token="T")
    with pytest.raises(ApiError) as error:
        api.overview()
    assert error.value.expired
    assert error.value.message == SESSION_EXPIRED


def test_validation_errors_are_never_echoed_back():
    body = {"detail": [{"input": "my secret password", "msg": "too short"}]}
    api, _ = client(FakeResponse(422, body))
    with pytest.raises(ApiError) as error:
        api.register("a@b.co", "my secret password", "A")
    assert error.value.message == "Please check what you entered."
    assert "secret" not in error.value.message


def test_server_errors_get_a_plain_message():
    api, _ = client(FakeResponse(500, None), token="T")
    with pytest.raises(ApiError) as error:
        api.overview()
    assert "try again" in error.value.message.lower()


def test_an_unreachable_server_is_explained():
    api, _ = client(fail=True)
    with pytest.raises(ApiError) as error:
        api.login("a@b.co", "pw")
    assert error.value.status == 0
    assert "API running" in error.value.message


def test_upload_sends_the_file_as_the_body_with_its_name():
    api, session = client(FakeResponse(202, {"id": "r1"}), token="T")
    assert api.upload_run("RFP-T.pdf", b"%PDF-1.4")["id"] == "r1"
    kwargs = session.calls[0][2]
    assert kwargs["content"] == b"%PDF-1.4"
    assert kwargs["headers"]["X-Filename"] == "RFP-T.pdf"
    assert kwargs["timeout"] > 30


def test_review_sends_only_the_expected_fields():
    api, session = client(FakeResponse(200, {"review_state": "edited"}), token="T")
    api.review("r1", "B-001", "edit", "partial", "I checked the policy.")
    method, url, kwargs = session.calls[0]
    assert url == "http://api.test/rfp/runs/r1/results/B-001/review"
    assert kwargs["json"] == {
        "action": "edit",
        "final_status": "partial",
        "note": "I checked the policy.",
    }


def test_export_returns_the_file_name_from_the_header():
    headers = {"content-disposition": 'attachment; filename="RFP-B_compliance_matrix.csv"'}
    api, _ = client(FakeResponse(200, None, headers, b"a,b\r\n"), token="T")
    download = api.export_csv("r1")
    assert (download.filename, download.data) == ("RFP-B_compliance_matrix.csv", b"a,b\r\n")


def test_a_blocked_export_explains_why():
    body = {"detail": "2 answer(s) still need review: B-001, B-002"}
    api, _ = client(FakeResponse(409, body), token="T")
    with pytest.raises(ApiError) as error:
        api.export_csv("r1")
    assert error.value.status == 409 and "still need review" in error.value.message


def test_ask_and_delete():
    api, session = client(FakeResponse(200, {"text": "hi"}), FakeResponse(204, None), token="T")
    api.ask("What is the uptime?", "c1")
    assert session.calls[0][2]["json"] == {
        "question": "What is the uptime?",
        "conversation_id": "c1",
    }
    assert api.delete_conversation("c1") is None


def test_public_ask_sends_no_token():
    api, session = client(FakeResponse(200, {"text": "hi"}))
    api.ask_public("What is the uptime?")
    assert "Authorization" not in session.calls[0][2]["headers"]
