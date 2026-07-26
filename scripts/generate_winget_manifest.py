"""Generate the WinGet singleton manifest for an x-cli release.

The script intentionally uses only the standard library so the manifest can
be reproduced in CI without adding a YAML runtime dependency to x-cli.
"""

from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path
from typing import Sequence
from urllib.parse import urlparse

from core.version import __version__


PACKAGE_IDENTIFIER = "XuanyuanLuoxue.XCLI"
MANIFEST_VERSION = "1.12.0"
_SEMVER_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")


class ReleaseInputError(ValueError):
    """Raised when release metadata cannot produce a safe manifest."""


def _validate_inputs(
    *,
    version: str,
    installer: Path,
    installer_url: str,
) -> None:
    if not _SEMVER_RE.fullmatch(version):
        raise ReleaseInputError("version must use X.Y.Z numeric format")
    if version != __version__:
        raise ReleaseInputError(
            f"release version {version} does not match source version {__version__}"
        )
    if not installer.is_file():
        raise ReleaseInputError(f"installer does not exist: {installer}")

    parsed_url = urlparse(installer_url)
    if parsed_url.scheme.lower() != "https" or not parsed_url.netloc:
        raise ReleaseInputError("installer URL must be an absolute HTTPS URL")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _render_manifest(*, version: str, installer_url: str, sha256: str) -> str:
    return f"""# Created by scripts/generate_winget_manifest.py
# yaml-language-server: $schema=https://aka.ms/winget-manifest.singleton.{MANIFEST_VERSION}.schema.json

PackageIdentifier: {PACKAGE_IDENTIFIER}
PackageVersion: {version}
PackageLocale: en-US
Publisher: Xavier
PublisherUrl: https://github.com/xuanyuanluoxue
PublisherSupportUrl: https://github.com/xuanyuanluoxue/x-cli/issues
Author: Xavier
PackageName: x-cli
PackageUrl: https://github.com/xuanyuanluoxue/x-cli
License: MIT
LicenseUrl: https://github.com/xuanyuanluoxue/x-cli/blob/v{version}/LICENSE
Copyright: Copyright (c) 2026 Xavier
ShortDescription: Local-first CLI for tasks, credentials, diaries, notes, and a Web UI.
Description: A zero-runtime-dependency personal CLI with local Markdown and JSON storage.
Moniker: x-cli
Tags:
- cli
- diary
- local-first
- notes
- productivity
- todo
InstallerType: portable
Commands:
- x
Installers:
- Architecture: x64
  InstallerUrl: {installer_url}
  InstallerSha256: {sha256}
ManifestType: singleton
ManifestVersion: {MANIFEST_VERSION}
"""


def generate_manifest(
    *,
    version: str,
    installer: Path,
    installer_url: str,
    output_root: Path,
) -> Path:
    """Validate release inputs and write a WinGet repository-shaped manifest."""
    installer = Path(installer).resolve()
    output_root = Path(output_root).resolve()
    _validate_inputs(
        version=version,
        installer=installer,
        installer_url=installer_url,
    )

    manifest_dir = (
        output_root
        / "manifests"
        / "x"
        / "XuanyuanLuoxue"
        / "XCLI"
        / version
    )
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / f"{PACKAGE_IDENTIFIER}.yaml"
    content = _render_manifest(
        version=version,
        installer_url=installer_url,
        sha256=_sha256(installer),
    )
    with manifest_path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(content)
    return manifest_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a validated WinGet manifest for x-cli."
    )
    parser.add_argument("--version", required=True, help="Release version (X.Y.Z)")
    parser.add_argument(
        "--installer",
        required=True,
        type=Path,
        help="Path to x-windows-x86_64.exe",
    )
    parser.add_argument("--url", required=True, help="Immutable HTTPS release URL")
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Output root that will receive manifests/x/...",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        path = generate_manifest(
            version=args.version,
            installer=args.installer,
            installer_url=args.url,
            output_root=args.output,
        )
    except ReleaseInputError as exc:
        parser.error(str(exc))
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
