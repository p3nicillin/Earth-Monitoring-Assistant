import asyncio
import uuid
from typing import Any

import pytest

from app.api import global_monitoring as global_api
from app.bootstrap import global_monitoring as bootstrap_module
from app.bootstrap.global_monitoring import (
    GLOBAL_MONITOR_EMAIL,
    GLOBAL_PROJECT_NAME,
    bootstrap_global_monitoring,
    get_cached_global_project_id,
)
from app.models.entities import Project, Role, User, WatchArea


def test_get_cached_global_project_id_raises_before_bootstrap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(bootstrap_module, "_global_project_id", None)
    with pytest.raises(RuntimeError, match="not been bootstrapped"):
        get_cached_global_project_id()


class _ScalarsResult:
    def __init__(self, items: list[Any]) -> None:
        self._items = list(items)

    def all(self) -> list[Any]:
        return self._items


class _FakeDB:
    def __init__(self) -> None:
        self.users: list[User] = []
        self.projects: list[Project] = []
        self.watch_areas: list[WatchArea] = []


class _FakeSession:
    def __init__(self, db: _FakeDB) -> None:
        self.db = db
        self._pending: list[Any] = []

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def scalar(self, stmt: Any) -> Any:
        entity = stmt.column_descriptions[0]["entity"]
        if entity is User:
            return next((u for u in self.db.users if u.email == GLOBAL_MONITOR_EMAIL), None)
        if entity is Project:
            return next((p for p in self.db.projects if p.name == GLOBAL_PROJECT_NAME), None)
        raise AssertionError(f"Unexpected scalar query for {entity}")

    async def scalars(self, stmt: Any) -> _ScalarsResult:
        entity = stmt.column_descriptions[0]["entity"]
        if entity is WatchArea:
            return _ScalarsResult([area.name for area in self.db.watch_areas])
        raise AssertionError(f"Unexpected scalars query for {entity}")

    def add(self, obj: Any) -> None:
        self._pending.append(obj)

    async def flush(self) -> None:
        for obj in self._pending:
            if obj.id is None:
                obj.id = uuid.uuid4()
            if isinstance(obj, User) and obj not in self.db.users:
                self.db.users.append(obj)
            elif isinstance(obj, Project) and obj not in self.db.projects:
                self.db.projects.append(obj)
            elif isinstance(obj, WatchArea) and obj not in self.db.watch_areas:
                self.db.watch_areas.append(obj)
        self._pending.clear()

    async def commit(self) -> None:
        await self.flush()


def test_bootstrap_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _FakeDB()
    monkeypatch.setattr(bootstrap_module, "SessionFactory", lambda: _FakeSession(db))
    monkeypatch.setattr(bootstrap_module, "_global_project_id", None)

    first_id = asyncio.run(bootstrap_global_monitoring())
    second_id = asyncio.run(bootstrap_global_monitoring())

    assert first_id == second_id
    assert len(db.users) == 1
    assert db.users[0].role == Role.system
    assert db.users[0].is_active is False
    assert len(db.projects) == 1
    assert len(db.watch_areas) == 6  # one per continent, not duplicated on the second call
    assert get_cached_global_project_id() == first_id


def test_filters_scope_to_global_project_only(monkeypatch: pytest.MonkeyPatch) -> None:
    fixed_id = uuid.uuid4()
    monkeypatch.setattr(global_api, "get_cached_global_project_id", lambda: fixed_id)

    filters = global_api._filters(None, None, None)

    assert len(filters) == 1
    rendered = str(filters[0].compile(compile_kwargs={"literal_binds": True}))
    assert "events.project_id" in rendered
    assert fixed_id.hex in rendered.replace("-", "")
    assert "owner_id" not in rendered  # never touches per-user ownership scoping
