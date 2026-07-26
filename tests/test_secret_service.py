"""Application-service contract shared by CLI and Web secret adapters."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.secret_service import SecretService
from core.secrets import (
    SecretAlreadyExistsError,
    SecretNotFoundError,
    SecretStore,
)
from plugins import secret as secret_plugin


@pytest.fixture
def store(tmp_path: Path) -> SecretStore:
    return SecretStore(db_path=tmp_path / "secrets.json")


@pytest.fixture
def service(store: SecretStore) -> SecretService:
    return SecretService(store)


def test_service_uses_injected_store_for_complete_lifecycle(
    service: SecretService,
    store: SecretStore,
) -> None:
    assert service.store is store

    created = service.create(
        "demo",
        value="secret-value",
        category="API",
        note="first note",
    )
    assert service.get("demo") == created
    assert service.find("DEM") == created
    assert service.list(category="api") == [created]
    assert service.search("first") == [created]

    updated = service.update("demo", note="changed")
    assert updated.note == "changed"
    assert service.delete("demo") == updated
    assert service.get("demo") is None


def test_service_preserves_domain_exceptions(service: SecretService) -> None:
    service.create("demo", value="one")

    with pytest.raises(SecretAlreadyExistsError):
        service.create("demo", value="two")
    with pytest.raises(SecretNotFoundError):
        service.update("missing", value="two")
    with pytest.raises(SecretNotFoundError):
        service.delete("missing")
    with pytest.raises(ValueError, match="value and fields"):
        service.create(
            "ambiguous",
            value="one",
            fields=[
                {
                    "label": "密钥",
                    "kind": "secret",
                    "value": "two",
                    "primary": True,
                }
            ],
        )


def test_service_import_and_export(
    service: SecretService,
    tmp_path: Path,
) -> None:
    source = tmp_path / "legacy"
    source.mkdir()
    (source / "API.md").write_text(
        "# API\n\n## Imported\n\n```text\nsk-imported\n```\n",
        encoding="utf-8",
    )

    assert service.import_from_dir(source) == (1, 0)
    exported = service.export(tmp_path / "backup.json")

    payload = json.loads(exported.read_text(encoding="utf-8"))
    assert payload["secrets"][0]["name"] == "Imported"


def test_default_service_uses_configured_secret_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "configured.json"
    monkeypatch.setenv("XCLI_SECRETS_DIR", str(db_path))

    service = SecretService()
    service.create("default-store", value="secret-value")

    assert service.store.db_path == db_path
    assert service.get("default-store") is not None


def test_cli_handlers_use_shared_service_factory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class RecordingService:
        def list(self, category=None):
            calls.append("list")
            return []

        def find(self, name):
            calls.append("find")
            return None

        def create(self, name, value=None, category="default", note=""):
            calls.append("create")
            return SimpleNamespace(name=name)

        def update(self, name, value=None, note=None, category=None):
            calls.append("update")
            return SimpleNamespace(name=name)

        def delete(self, name):
            calls.append("delete")
            return SimpleNamespace(name=name)

        def search(self, keyword):
            calls.append("search")
            return []

        def import_from_dir(self, src_dir):
            calls.append("import")
            return 0, 0

        def export(self, dest=None):
            calls.append("export")
            return dest or tmp_path / "backup.json"

    recording = RecordingService()
    monkeypatch.setenv("XCLI_SECRETS_DIR", str(tmp_path / "secrets.json"))
    monkeypatch.setattr(
        secret_plugin,
        "_secret_service",
        lambda: recording,
        raising=False,
    )

    assert secret_plugin._secret_list(SimpleNamespace(category=None)) == 0
    assert (
        secret_plugin._secret_get(
            SimpleNamespace(
                name="missing",
                full=False,
                field_label=None,
                no_stdout=False,
                no_clipboard=True,
            )
        )
        == 3
    )
    assert (
        secret_plugin._secret_set(
            SimpleNamespace(
                name="demo",
                value="secret-value",
                category="API",
                note="",
            )
        )
        == 0
    )
    assert (
        secret_plugin._secret_update(
            SimpleNamespace(
                name="demo",
                value="new-value",
                note=None,
                category=None,
            )
        )
        == 0
    )
    assert secret_plugin._secret_rm(SimpleNamespace(name="demo")) == 0
    assert secret_plugin._secret_search(SimpleNamespace(keyword="demo")) == 0
    source = tmp_path / "legacy"
    source.mkdir()
    assert secret_plugin._secret_import(SimpleNamespace(src_dir=str(source))) == 0
    assert (
        secret_plugin._secret_export(
            SimpleNamespace(dest=str(tmp_path / "backup.json"))
        )
        == 0
    )

    assert calls == [
        "list",
        "find",
        "create",
        "update",
        "delete",
        "search",
        "import",
        "export",
        "list",
    ]
