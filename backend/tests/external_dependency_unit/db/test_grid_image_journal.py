"""Image claim/recovery proofs on real Postgres in a disposable schema."""

import importlib.util
import os
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import ModuleType
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine
from sqlalchemy import inspect
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

from onyx.db.grid_image_requests import claim_image_request
from onyx.db.grid_image_requests import finish_image_request
from onyx.db.grid_image_requests import ImageRequestConflict
from onyx.db.grid_image_requests import read_image_request
from onyx.db.models import GridImageRequest

OWNER = uuid4()
OTHER = uuid4()


def migration() -> ModuleType:
    path = (
        Path(__file__).resolve().parents[3]
        / "alembic/versions/a1f092c7d8e3_grid_image_recovery_journal.py"
    )
    spec = importlib.util.spec_from_file_location("image_journal_migration", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def journal() -> Generator[sessionmaker[Session], None, None]:
    url = os.environ.get("AIPG_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("AIPG_TEST_POSTGRES_URL must point to a disposable Postgres")
    schema = "test_image_journal_" + uuid4().hex
    admin = create_engine(url)
    assert admin.dialect.name == "postgresql"
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(
        url, connect_args={"options": f"-csearch_path={schema}"}, pool_size=32
    )
    try:
        with engine.begin() as conn:
            conn.execute(text('CREATE TABLE "user" (id uuid PRIMARY KEY)'))
            conn.execute(
                text(
                    'CREATE TABLE chat_session (id uuid PRIMARY KEY, user_id uuid REFERENCES "user"(id))'
                )
            )
            conn.execute(
                text(
                    "CREATE TABLE chat_message (id integer PRIMARY KEY, chat_session_id uuid REFERENCES chat_session(id), message_type varchar)"
                )
            )
            conn.execute(
                text('INSERT INTO "user" (id) VALUES (:owner), (:other)'),
                {"owner": OWNER, "other": OTHER},
            )
            session_id = uuid4()
            conn.execute(
                text("INSERT INTO chat_session VALUES (:id, :owner)"),
                {"id": session_id, "owner": OWNER},
            )
            conn.execute(
                text(
                    "INSERT INTO chat_message VALUES (1, :id, 'ASSISTANT'), (2, :id, 'USER')"
                ),
                {"id": session_id},
            )
            with Operations.context(MigrationContext.configure(conn)):
                migration().upgrade()
        yield sessionmaker(engine)
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def claim(journal: sessionmaker[Session], slot: str = "0:0:0", digest: str = "a" * 64):
    with journal() as session:
        return claim_image_request(
            session, user_id=OWNER, message_id=1, slot=slot, request_sha256=digest
        )


def test_twenty_five_racers_receive_one_submission_permission(
    journal: sessionmaker[Session],
) -> None:
    with ThreadPoolExecutor(max_workers=25) as pool:
        receipts = list(pool.map(lambda _: claim(journal), range(25)))
    assert sum(r.may_submit for r in receipts) == 1
    assert len({r.id for r in receipts}) == 1
    assert all(r.state == "attempted" for r in receipts)
    # New session/process-equivalent never reclaims a possibly dispatched POST.
    assert not claim(journal).may_submit


def test_batch_items_are_distinct_but_changed_payload_cannot_reuse_slot(
    journal: sessionmaker[Session],
) -> None:
    a, b = claim(journal, "image:0"), claim(journal, "image:1")
    assert a.id != b.id and a.may_submit and b.may_submit
    with pytest.raises(ImageRequestConflict):
        claim(journal, "image:0", "b" * 64)
    assert claim(journal, "image:0").id == a.id


def test_owner_is_checked_for_claim_read_and_finish(
    journal: sessionmaker[Session],
) -> None:
    row = claim(journal)
    with journal() as session:
        with pytest.raises(ImageRequestConflict):
            claim_image_request(
                session,
                user_id=OTHER,
                message_id=1,
                slot="new",
                request_sha256="a" * 64,
            )
        assert read_image_request(session, user_id=OTHER, request_id=row.id) is None
        with pytest.raises(ImageRequestConflict):
            finish_image_request(
                session,
                user_id=OTHER,
                request_id=row.id,
                grid_job_id=uuid4(),
                result={},
            )


def test_user_message_cannot_be_used_as_an_assistant_request_slot(
    journal: sessionmaker[Session],
) -> None:
    with journal() as session, pytest.raises(ImageRequestConflict):
        claim_image_request(
            session,
            user_id=OWNER,
            message_id=2,
            slot="image:0",
            request_sha256="a" * 64,
        )


def test_commit_failure_never_returns_submission_permission(
    journal: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_commit() -> None:
        raise RuntimeError("test commit failure")

    with journal() as session:
        monkeypatch.setattr(session, "commit", fail_commit)
        with pytest.raises(RuntimeError, match="test commit failure"):
            claim_image_request(
                session,
                user_id=OWNER,
                message_id=1,
                slot="image:0",
                request_sha256="a" * 64,
            )
    assert claim(journal, "image:0").may_submit


@pytest.mark.parametrize(
    "result", [None, {"media": [{"url": "https://example.test/image.png"}]}]
)
def test_terminal_is_committed_and_duplicate_safe(
    journal: sessionmaker[Session], result: dict | None
) -> None:
    row, job = claim(journal), uuid4()

    def finish(_: int):
        with journal() as session:
            return finish_image_request(
                session,
                user_id=OWNER,
                request_id=row.id,
                grid_job_id=job,
                result=result,
            )

    with ThreadPoolExecutor(max_workers=12) as pool:
        receipts = list(pool.map(finish, range(12)))
    assert all(
        r.state == ("completed" if result is not None else "closed") for r in receipts
    )
    with journal() as session:
        recovered = read_image_request(session, user_id=OWNER, request_id=row.id)
        assert recovered and recovered.result == result and recovered.grid_job_id == job
        with pytest.raises(ImageRequestConflict):
            finish_image_request(
                session,
                user_id=OWNER,
                request_id=row.id,
                grid_job_id=uuid4(),
                result=result,
            )
    assert not claim(journal).may_submit


def test_populated_journal_cannot_be_downgraded(journal: sessionmaker[Session]) -> None:
    row = claim(journal)
    with journal() as session:
        with Operations.context(MigrationContext.configure(session.connection())):
            with pytest.raises(RuntimeError, match="nonempty"):
                migration().downgrade()
    with journal() as session:
        assert read_image_request(session, user_id=OWNER, request_id=row.id)


def test_conflicting_terminal_race_preserves_one_outcome(
    journal: sessionmaker[Session],
) -> None:
    row, job = claim(journal), uuid4()

    def finish(index: int):
        with journal() as session:
            try:
                return finish_image_request(
                    session,
                    user_id=OWNER,
                    request_id=row.id,
                    grid_job_id=job,
                    result={"media": []} if index % 2 else None,
                )
            except ImageRequestConflict:
                return None

    with ThreadPoolExecutor(max_workers=12) as pool:
        receipts = list(pool.map(finish, range(12)))
    successes = [r for r in receipts if r is not None]
    assert len(successes) == 6
    assert len({r.state for r in successes}) == 1
    with journal() as session:
        stored = read_image_request(session, user_id=OWNER, request_id=row.id)
        assert stored and stored.state == successes[0].state


def test_migration_matches_model_contract(journal: sessionmaker[Session]) -> None:
    with journal() as session:
        inspector = inspect(session.connection())
        table_name = "grid_image_request"
        columns = inspector.get_columns("grid_image_request")
        model = GridImageRequest.__table__
        assert {c["name"]: c["nullable"] for c in columns} == {
            c.name: c.nullable for c in model.columns
        }
        dialect = session.get_bind().dialect
        assert {c["name"]: c["type"].compile(dialect=dialect) for c in columns} == {
            c.name: c.type.compile(dialect=dialect) for c in model.columns
        }
        assert {c["name"] for c in inspector.get_check_constraints(table_name)} == {
            "ck_grid_image_request_state",
            "ck_grid_image_request_result",
        }
        assert inspector.get_unique_constraints(table_name)[0]["column_names"] == [
            "message_id",
            "slot",
        ]
        assert {
            tuple(fk["constrained_columns"])
            for fk in inspector.get_foreign_keys(table_name)
        } == {("user_id",), ("message_id",)}
