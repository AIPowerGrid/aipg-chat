"""Real provider/HTTP transport against a local Grid stand-in; no paid inference."""

import json
import threading
from collections import OrderedDict
from collections.abc import Generator
from dataclasses import dataclass
from dataclasses import field
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
from types import SimpleNamespace
from typing import Any
from typing import cast
from uuid import uuid4

import pytest
from openai import APIError

from onyx.db.models import User
from onyx.image_gen.providers.openai_img_gen import OpenAIImageGenerationProvider
from onyx.llm.aipg import identity_assertion as identity


@dataclass
class GridStandIn:
    base: str = ""
    image_status: int = 200
    identity_status: int = 200
    drop_response: bool = False
    requests: list[dict[str, Any]] = field(default_factory=list)


@pytest.fixture
def grid_http(monkeypatch: pytest.MonkeyPatch) -> Generator[GridStandIn, None, None]:
    grid = GridStandIn()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass

        def do_POST(self) -> None:
            payload: dict[str, Any]
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            grid.requests.append(
                {
                    "path": self.path,
                    "apikey": self.headers.get("apikey"),
                    "authorization": self.headers.get("authorization"),
                    "delegated": self.headers.get("X-Grid-User-Token"),
                    "body": body,
                }
            )
            if self.path == "/v1/auth/service/exchange":
                status = grid.identity_status
                payload = {
                    "access_token": "gridu_test_" + body["subject"],
                    "account_id": body["subject"].split(":")[-1],
                    "expires_in": 900,
                }
            elif self.path == "/v1/images/generations":
                if grid.drop_response:
                    self.close_connection = True
                    return
                status = grid.image_status
                payload = {"created": 1, "data": [{"b64_json": "dGVzdA=="}]}
            else:
                status = 404
                payload = {}
            if status != 200:
                payload = {
                    "error": {"message": "fixture rejected", "type": "test_error"}
                }
            raw = json.dumps(payload).encode()
            self.send_response(status)
            if 300 <= status < 400:
                self.send_header("Location", "/unexpected-redirect")
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    grid.base = f"http://127.0.0.1:{server.server_port}/v1"
    monkeypatch.setenv("AIPG_GRID_API_BASE", grid.base)
    monkeypatch.setenv("AIPG_GRID_API_KEY", "grid_test_image_bridge")
    monkeypatch.setenv("LITELLM_LOCAL_MODEL_COST_MAP", "true")
    monkeypatch.setattr(identity, "_token_cache", OrderedDict())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield grid
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


def image_request(
    grid: GridStandIn,
    user_id: str,
    provider: OpenAIImageGenerationProvider | None = None,
) -> None:
    user = cast(User, SimpleNamespace(id=user_id, is_anonymous=False))
    headers = identity.grid_image_headers_factory(
        grid.base, "grid_test_image_bridge", user
    )
    assert headers is not None
    provider = provider or OpenAIImageGenerationProvider(
        api_key="grid_test_image_bridge", api_base=grid.base
    )
    response = provider.generate_image(
        prompt="transport canary",
        model="Krea 2 Turbo",
        size="1024x1024",
        n=1,
        response_format="b64_json",
        extra_headers=headers(),
    )
    assert response.data and response.data[0].b64_json == "dGVzdA=="


def test_grid_identity_reaches_image_http_without_cross_user_reuse(
    grid_http: GridStandIn,
) -> None:
    users = [str(uuid4()), str(uuid4())]
    provider = OpenAIImageGenerationProvider(
        api_key="grid_test_image_bridge", api_base=grid_http.base
    )
    for user_id in users:
        image_request(grid_http, user_id, provider)
    images = [r for r in grid_http.requests if r["path"] == "/v1/images/generations"]
    assert len(images) == 2
    assert [r["delegated"] for r in images] == [
        f"gridu_test_aipg-chat:{user_id}" for user_id in users
    ]
    assert all(r["authorization"] == "Bearer grid_test_image_bridge" for r in images)
    assert all(r["body"]["model"] == "Krea 2 Turbo" for r in images)
    assert all(r["body"]["response_format"] == "b64_json" for r in images)
    for request in images:
        body = json.dumps(request["body"])
        assert "gridu_test_" not in body
        assert "grid_test_image_bridge" not in body
        assert "extra_headers" not in request["body"]


@pytest.mark.parametrize(
    "status", [302, 307, 308, 401, 402, 429, 500, 503, "lost-response"]
)
def test_image_failure_never_automatically_reposts_paid_work(
    grid_http: GridStandIn, status: int | str
) -> None:
    grid_http.drop_response = status == "lost-response"
    if isinstance(status, int):
        grid_http.image_status = status
    with pytest.raises(APIError):
        image_request(grid_http, str(uuid4()))
    images = [r for r in grid_http.requests if r["path"] == "/v1/images/generations"]
    assert len(images) == 1, "uncertain image outcome was submitted more than once"
    assert not any(r["path"] == "/unexpected-redirect" for r in grid_http.requests)


def test_identity_outage_dispatches_no_image(grid_http: GridStandIn) -> None:
    grid_http.identity_status = 503
    with pytest.raises(identity.GridIdentityError):
        image_request(grid_http, str(uuid4()))
    assert [r["path"] for r in grid_http.requests] == ["/v1/auth/service/exchange"]
