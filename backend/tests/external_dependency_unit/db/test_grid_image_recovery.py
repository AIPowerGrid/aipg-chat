"""Real Postgres journal + real SDK/HTTP; the local Core stand-in moves no money."""

import json
import os
import subprocess
import sys
import threading
from collections.abc import Generator
from dataclasses import dataclass
from dataclasses import field
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

from onyx.db.grid_image_requests import ImageRequestConflict
from onyx.db.grid_image_requests import list_image_requests
from onyx.image_gen.providers.openai_img_gen import OpenAIImageGenerationProvider
from onyx.llm.aipg.image_recovery import GridImageRecovery
from onyx.llm.aipg.image_recovery import GridImageRecoveryError
from tests.external_dependency_unit.db.test_grid_image_journal import (
    journal as _journal,
)
from tests.external_dependency_unit.db.test_grid_image_journal import OTHER
from tests.external_dependency_unit.db.test_grid_image_journal import OWNER

journal = _journal


@dataclass
class Core:
    base: str = ""
    charging: bool = True
    ready: bool = True
    drop_response: bool = False
    generation_status: int = 200
    recovery_status: int = 200
    requests: list[dict[str, Any]] = field(default_factory=list)
    jobs: dict[str, dict[str, Any]] = field(default_factory=dict)
    post_seen: threading.Event = field(default_factory=threading.Event)
    hold_response: threading.Event | None = None


@pytest.fixture
def core() -> Generator[Core, None, None]:
    state = Core()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass

        def reply(self, status: int, payload: dict) -> None:
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self) -> None:
            state.requests.append({"method": "GET", "path": self.path})
            path = urlsplit(self.path)
            if path.path == "/v1/account/credits":
                self.reply(200, {"charging_enabled": state.charging})
                return
            ref = parse_qs(path.query).get("client_ref", [""])[0]
            if (
                path.path != "/v1/media/results"
                or not state.ready
                or ref not in state.jobs
            ):
                self.reply(404, {"detail": "not found"})
                return
            self.reply(state.recovery_status, state.jobs[ref])

        def do_POST(self) -> None:
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            state.requests.append(
                {
                    "method": "POST",
                    "path": self.path,
                    "body": body,
                    "token": self.headers.get("X-Grid-User-Token"),
                }
            )
            if state.generation_status != 200:
                self.reply(state.generation_status, {"detail": "test rejection"})
                return
            ref = body["progress_token"]
            job = str(uuid4())
            state.jobs[ref] = {
                "job_id": job,
                "state": "completed",
                "actual_micro": 3000,
                "result": {
                    "media": [
                        {
                            "url": "https://example.test/test.png",
                            "key": "test.png",
                            "sha256": "a" * 64,
                            "seed": 1,
                        }
                    ],
                    "model": body["model"],
                    "worker": "test-worker",
                    "gen_time": 1.0,
                    "recipe_root": None,
                },
            }
            state.post_seen.set()
            if state.hold_response is not None:
                state.hold_response.wait(timeout=30)
            if state.drop_response:
                self.close_connection = True
                return
            self.reply(
                200,
                {
                    "created": 1,
                    "data": [{"url": "https://example.test/test.png"}],
                    "grid": {"job_id": job},
                },
            )

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    state.base = f"http://127.0.0.1:{server.server_port}/v1"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


def service(core: Core, journal: sessionmaker[Session]) -> GridImageRecovery:
    return GridImageRecovery(
        user_id=OWNER,
        api_base=core.base,
        api_key="grid_test_bridge",
        headers_factory=lambda: {"X-Grid-User-Token": "gridu_test"},
        sessions=journal,
    )


def generate(core: Core, journal: sessionmaker[Session], slot: str = "image:0"):
    return service(core, journal).generate(
        provider=OpenAIImageGenerationProvider(
            api_key="grid_test_bridge", api_base=core.base
        ),
        message_id=1,
        slot=slot,
        prompt="test image",
        model="Krea 2 Turbo",
        size="1024x1024",
    )


def posts(core: Core) -> list[dict[str, Any]]:
    return [r for r in core.requests if r["method"] == "POST"]


@pytest.mark.parametrize("drop_response", [False, True])
def test_new_instance_recovers_original_result_without_second_post(
    core: Core,
    journal: sessionmaker[Session],
    drop_response: bool,
) -> None:
    core.drop_response = drop_response
    first = generate(core, journal)
    second = generate(core, journal)
    assert first.id == second.id and first.result == second.result
    assert first.state == second.state == "completed"
    assert len(posts(core)) == 1
    request = posts(core)[0]
    assert request["body"]["progress_token"] == str(first.id)
    assert request["token"] == "gridu_test"
    assert "gridu_test" not in json.dumps(request["body"])


def test_lost_response_pending_then_recovery_never_regenerates(
    core: Core,
    journal: sessionmaker[Session],
) -> None:
    core.drop_response, core.ready = True, False
    with pytest.raises(GridImageRecoveryError):
        generate(core, journal)
    with journal() as session:
        request = list_image_requests(session, user_id=OWNER, message_id=1)[0]
    pending = service(core, journal).recover(request.id)
    assert pending and pending.state == "attempted"
    with pytest.raises(GridImageRecoveryError):
        generate(core, journal)
    with pytest.raises(ImageRequestConflict, match="new user request"):
        generate(core, journal, "new-tool-call:0")
    core.ready = True
    recovered = service(core, journal).recover(request.id)
    assert recovered and recovered.state == "completed"
    assert len(posts(core)) == 1


def test_preview_account_is_rejected_before_generation(
    core: Core, journal: sessionmaker[Session]
) -> None:
    core.charging = False
    with pytest.raises(GridImageRecoveryError, match="not enabled"):
        generate(core, journal)
    assert posts(core) == []


def test_insufficient_credit_is_actionable_without_retry(
    core: Core,
    journal: sessionmaker[Session],
) -> None:
    core.generation_status = 402
    with pytest.raises(GridImageRecoveryError, match="Insufficient image credits"):
        generate(core, journal)
    assert len(posts(core)) == 1


@pytest.mark.parametrize(
    "invalid", ["missing-cost", "invalid-hash", "pending-with-result"]
)
def test_invalid_core_terminal_is_not_recorded(
    core: Core,
    journal: sessionmaker[Session],
    invalid: str,
) -> None:
    core.ready = False
    with pytest.raises(GridImageRecoveryError):
        generate(core, journal)
    ref, payload = next(iter(core.jobs.items()))
    if invalid == "missing-cost":
        payload["actual_micro"] = None
    elif invalid == "invalid-hash":
        payload["result"]["media"][0]["sha256"] = "invalid"
    else:
        payload["state"] = "pending"
    core.ready = True
    from uuid import UUID

    with pytest.raises(GridImageRecoveryError, match="invalid recovery"):
        service(core, journal).recover(UUID(ref))
    with journal() as session:
        assert (
            list_image_requests(session, user_id=OWNER, message_id=1)[0].state
            == "attempted"
        )
    assert len(posts(core)) == 1


def test_foreign_owner_recovery_makes_no_core_call(
    core: Core, journal: sessionmaker[Session]
) -> None:
    receipt = generate(core, journal)
    before = len(core.requests)
    foreign = GridImageRecovery(
        user_id=OTHER,
        api_base=core.base,
        api_key="grid_test_bridge",
        headers_factory=lambda: {"X-Grid-User-Token": "gridu_other"},
        sessions=journal,
    )
    assert foreign.recover(receipt.id) is None
    assert len(core.requests) == before


def test_partial_batch_keeps_first_result_and_does_not_retry_failure(
    core: Core, journal: sessionmaker[Session]
) -> None:
    first = generate(core, journal, "image:0")
    core.generation_status = 503
    with pytest.raises(GridImageRecoveryError):
        generate(core, journal, "image:1")
    with pytest.raises(GridImageRecoveryError):
        generate(core, journal, "image:1")
    recovered = service(core, journal).recover(first.id)
    assert recovered and recovered.state == "completed"
    assert len(posts(core)) == 2


def test_unavailable_recovery_does_not_close_or_resubmit(
    core: Core, journal: sessionmaker[Session]
) -> None:
    core.drop_response, core.recovery_status = True, 503
    with pytest.raises(GridImageRecoveryError):
        generate(core, journal)
    with journal() as session:
        receipt = list_image_requests(session, user_id=OWNER, message_id=1)[0]
    assert receipt.state == "attempted"
    core.recovery_status = 200
    recovered = service(core, journal).recover(receipt.id)
    assert recovered and recovered.state == "completed"
    assert len(posts(core)) == 1


def test_killed_process_recovers_committed_claim_without_new_post(
    core: Core,
    journal: sessionmaker[Session],
) -> None:
    with journal() as session:
        schema = session.scalar(text("SELECT current_schema()"))
        dsn = session.get_bind().engine.url.render_as_string(hide_password=False)
    core.hold_response = threading.Event()
    script = """
import os
from uuid import UUID
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from onyx.llm.aipg.image_recovery import GridImageRecovery
from onyx.image_gen.providers.openai_img_gen import OpenAIImageGenerationProvider
base = os.environ['TEST_CORE_BASE']
engine = create_engine(os.environ['TEST_DSN'], connect_args={'options': '-csearch_path=' + os.environ['TEST_SCHEMA']})
service = GridImageRecovery(user_id=UUID(os.environ['TEST_OWNER']), api_base=base,
    api_key='grid_test_bridge', headers_factory=lambda: {'X-Grid-User-Token': 'gridu_test'}, sessions=sessionmaker(engine))
service.generate(provider=OpenAIImageGenerationProvider(api_key='grid_test_bridge', api_base=base),
    message_id=1, slot='image:0', prompt='test image', model='Krea 2 Turbo', size='1024x1024')
"""
    child = subprocess.Popen(
        [sys.executable, "-c", script],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env={
            **os.environ,
            "TEST_CORE_BASE": core.base,
            "TEST_DSN": dsn,
            "TEST_SCHEMA": schema,
            "TEST_OWNER": str(OWNER),
        },
    )
    try:
        assert core.post_seen.wait(timeout=20), "Child never reached generation POST"
        assert child.poll() is None
        child.kill()
        child.communicate(timeout=10)
        with journal() as session:
            receipt = list_image_requests(session, user_id=OWNER, message_id=1)[0]
        assert receipt.state == "attempted"
        recovered = service(core, journal).recover(receipt.id)
        assert recovered and recovered.state == "completed"
        assert len(posts(core)) == 1
    finally:
        core.hold_response.set()
        if child.poll() is None:
            child.kill()
        child.communicate(timeout=10)


def test_recovery_routes_are_owner_scoped_and_private(
    core: Core,
    journal: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from onyx.db.models import User
    from onyx.error_handling.error_codes import OnyxErrorCode
    from onyx.error_handling.exceptions import OnyxError
    from onyx.server.manage.llm import grid_status

    receipt = generate(core, journal)
    monkeypatch.setattr(grid_status, "get_session_with_current_tenant", journal)

    def for_user(user):
        instance = service(core, journal)
        instance.user_id = user.id
        return instance

    monkeypatch.setattr(grid_status, "recovery_for_user", for_user)
    response = grid_status.get_grid_image_requests(1, User(id=OWNER))
    assert response.headers["Cache-Control"] == "no-store"
    assert json.loads(bytes(response.body))["requests"][0]["request_id"] == str(
        receipt.id
    )
    assert json.loads(
        bytes(grid_status.get_grid_image_requests(1, User(id=OTHER)).body)
    ) == {"requests": []}
    with pytest.raises(OnyxError) as caught:
        grid_status.recover_grid_image_request(receipt.id, User(id=OTHER))
    assert caught.value.error_code == OnyxErrorCode.NOT_FOUND
    recovered = grid_status.recover_grid_image_request(receipt.id, User(id=OWNER))
    assert recovered.headers["Cache-Control"] == "no-store"
    assert json.loads(bytes(recovered.body))["state"] == "completed"
