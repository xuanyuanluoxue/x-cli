"""Shared application service for CLI and Web secret operations.

The service is deliberately protocol-agnostic: it owns the application-facing
operation names, while :mod:`plugins.secret` and :mod:`core.web` retain their
own presentation and error mapping. JSON schema, validation, locking and
persistence stay in :class:`core.secrets.SecretStore`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.secrets import SecretEntry, SecretField, SecretStore


class SecretService:
    """Application API shared by the CLI and Web adapters."""

    def __init__(self, store: SecretStore | None = None) -> None:
        self.store = store if store is not None else SecretStore()

    def list(self, category: str | None = None) -> list[SecretEntry]:
        return self.store.list(category=category)

    def get(self, name: str) -> SecretEntry | None:
        return self.store.get(name)

    def find(self, name: str) -> SecretEntry | None:
        return self.store.find(name)

    def search(self, keyword: str) -> list[SecretEntry]:
        return self.store.search(keyword)

    def create(
        self,
        name: str,
        value: str | None = None,
        category: str = "default",
        note: str = "",
        *,
        fields: list[SecretField | dict[str, Any]] | None = None,
    ) -> SecretEntry:
        return self.store.set(
            name=name,
            value=value,
            category=category,
            note=note,
            fields=fields,
        )

    def update(
        self,
        name: str,
        value: str | None = None,
        note: str | None = None,
        category: str | None = None,
        *,
        fields: list[SecretField | dict[str, Any]] | None = None,
    ) -> SecretEntry:
        return self.store.update(
            name=name,
            value=value,
            note=note,
            category=category,
            fields=fields,
        )

    def delete(self, name: str) -> SecretEntry:
        return self.store.rm(name)

    def import_from_dir(self, src_dir: Path) -> tuple[int, int]:
        return self.store.import_from_dir(src_dir)

    def export(self, dest: Path | None = None) -> Path:
        return self.store.export(dest)
