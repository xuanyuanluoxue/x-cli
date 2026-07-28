"""发行与 WinGet 行为测试。

BDD: docs/behaviors/distribution-behavior.md
"""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path

import pytest

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised by Python 3.10 CI
    import tomli as tomllib


ROOT = Path(__file__).resolve().parents[1]


def _pyproject() -> dict[str, object]:
    return tomllib.loads(
        (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )


def test_project_uses_dynamic_single_source_version():
    config = _pyproject()

    assert "version" not in config["project"]
    assert "version" in config["project"]["dynamic"]
    assert (
        config["tool"]["setuptools"]["dynamic"]["version"]["attr"]
        == "core.version.__version__"
    )


def test_cli_imports_version_instead_of_defining_another_constant():
    from core.version import __version__ as source_version
    from x import __version__ as cli_version

    assert source_version == "0.8.0"
    assert cli_version == source_version

    module = ast.parse((ROOT / "x.py").read_text(encoding="utf-8"))
    assignments = {
        target.id
        for node in ast.walk(module)
        if isinstance(node, (ast.Assign, ast.AnnAssign))
        for target in (
            node.targets if isinstance(node, ast.Assign) else [node.target]
        )
        if isinstance(target, ast.Name)
    }
    assert "__version__" not in assignments


def test_setuptools_discovers_subpackages_and_web_static_assets():
    config = _pyproject()
    setuptools = config["tool"]["setuptools"]

    assert setuptools["packages"]["find"]["include"] == [
        "core*",
        "plugins*",
    ]
    assert "static/**/*" in setuptools["package-data"]["core.web"]


def test_release_dependencies_do_not_become_runtime_dependencies():
    project = _pyproject()["project"]

    assert project["dependencies"] == []
    release = project["optional-dependencies"]["release"]
    assert any(item.startswith("build") for item in release)
    assert any(item.startswith("pyinstaller") for item in release)


def test_pyinstaller_spec_builds_console_exe_with_web_assets():
    spec = (ROOT / "packaging" / "x-cli.spec").read_text(encoding="utf-8")

    assert 'collect_data_files("core.web")' in spec
    assert 'collect_submodules("plugins")' in spec
    assert "hiddenimports=PLUGIN_MODULES" in spec
    assert 'name="x-windows-x86_64"' in spec
    assert "console=True" in spec
    assert "upx=False" in spec
    assert "uac_admin=True" not in spec


def test_windows_build_script_runs_release_smoke_tests_and_hashes():
    script = (ROOT / "scripts" / "build-windows.ps1").read_text(
        encoding="utf-8"
    )

    assert "-m build --no-isolation" in script
    assert "-m PyInstaller" in script
    assert "--version" in script
    assert '"note", "--help"' in script
    assert "Get-FileHash" in script
    assert "x-windows-x86_64.exe.sha256" in script
    assert "Start-Process" in script
    assert "-WindowStyle Hidden" in script
    assert "Invoke-WebRequest" in script
    assert "release-smoke-token" in script


def test_windows_build_script_forces_utf8_for_child_processes_and_restores_env():
    script = (ROOT / "scripts" / "build-windows.ps1").read_text(
        encoding="utf-8"
    )

    assert '$env:PYTHONUTF8 = "1"' in script
    assert '$env:PYTHONIOENCODING = "utf-8"' in script
    assert "PreviousPythonUtf8" in script
    assert "PreviousPythonIoEncoding" in script
    assert "Remove-Item Env:PYTHONUTF8" in script
    assert "Remove-Item Env:PYTHONIOENCODING" in script


def test_windows_build_script_captures_exe_output_as_utf8():
    script = (ROOT / "scripts" / "build-windows.ps1").read_text(
        encoding="utf-8"
    )

    assert "Invoke-CapturedUtf8Process" in script
    assert "System.Diagnostics.ProcessStartInfo" in script
    assert "StandardOutputEncoding" in script
    assert "StandardErrorEncoding" in script
    assert ".ExitCode" in script


def test_windows_build_script_cleans_up_onefile_web_children():
    script = (ROOT / "scripts" / "build-windows.ps1").read_text(
        encoding="utf-8"
    )

    assert "Get-CimInstance Win32_Process" in script
    assert "ExecutablePath -eq $Executable" in script
    assert "$ExistingExecutableProcessIds" in script
    assert "Stop-Process -Id $ProcessId -Force" in script


def test_generate_winget_manifest_uses_real_hash_and_release_metadata(tmp_path):
    from scripts.generate_winget_manifest import generate_manifest

    installer = tmp_path / "x-windows-x86_64.exe"
    installer.write_bytes(b"deterministic-test-installer")
    url = (
        "https://github.com/xuanyuanluoxue/x-cli/releases/download/"
        "v0.8.0/x-windows-x86_64.exe"
    )

    manifest_dir = generate_manifest(
        version="0.8.0",
        installer=installer,
        installer_url=url,
        output_root=tmp_path / "output",
    )

    expected_hash = hashlib.sha256(installer.read_bytes()).hexdigest().upper()
    assert manifest_dir == (
        tmp_path
        / "output"
        / "manifests"
        / "x"
        / "XuanyuanLuoxue"
        / "XCLI"
        / "0.8.0"
    )
    assert sorted(path.name for path in manifest_dir.glob("*.yaml")) == [
        "XuanyuanLuoxue.XCLI.installer.yaml",
        "XuanyuanLuoxue.XCLI.locale.en-US.yaml",
        "XuanyuanLuoxue.XCLI.yaml",
    ]

    version_text = (
        manifest_dir / "XuanyuanLuoxue.XCLI.yaml"
    ).read_text(encoding="utf-8")
    installer_text = (
        manifest_dir / "XuanyuanLuoxue.XCLI.installer.yaml"
    ).read_text(encoding="utf-8")
    locale_text = (
        manifest_dir / "XuanyuanLuoxue.XCLI.locale.en-US.yaml"
    ).read_text(encoding="utf-8")

    for expected in (
        "PackageIdentifier: XuanyuanLuoxue.XCLI",
        "PackageVersion: 0.8.0",
        "DefaultLocale: en-US",
        "ManifestType: version",
        "ManifestVersion: 1.12.0",
    ):
        assert expected in version_text

    for expected in (
        "PackageIdentifier: XuanyuanLuoxue.XCLI",
        "PackageVersion: 0.8.0",
        "InstallerType: portable",
        "Architecture: x64",
        "Commands:",
        "- x",
        f"InstallerUrl: {url}",
        f"InstallerSha256: {expected_hash}",
        "ManifestType: installer",
        "ManifestVersion: 1.12.0",
    ):
        assert expected in installer_text

    for expected in (
        "PackageIdentifier: XuanyuanLuoxue.XCLI",
        "PackageVersion: 0.8.0",
        "PackageLocale: en-US",
        "Publisher: Xavier",
        "PackageName: x-cli",
        "ManifestType: defaultLocale",
        "ManifestVersion: 1.12.0",
    ):
        assert expected in locale_text

    combined = version_text + installer_text + locale_text
    assert "ManifestType: singleton" not in combined


@pytest.mark.parametrize("version", ["v0.7.0", "0.7", "latest", "0.7.0.1"])
def test_generate_winget_manifest_rejects_non_semver(version, tmp_path):
    from scripts.generate_winget_manifest import ReleaseInputError, generate_manifest

    installer = tmp_path / "x.exe"
    installer.write_bytes(b"exe")

    with pytest.raises(ReleaseInputError, match="X.Y.Z"):
        generate_manifest(
            version=version,
            installer=installer,
            installer_url="https://example.com/x.exe",
            output_root=tmp_path / "output",
        )


def test_generate_winget_manifest_rejects_non_https_url(tmp_path):
    from scripts.generate_winget_manifest import ReleaseInputError, generate_manifest

    installer = tmp_path / "x.exe"
    installer.write_bytes(b"exe")

    with pytest.raises(ReleaseInputError, match="HTTPS"):
        generate_manifest(
            version="0.8.0",
            installer=installer,
            installer_url="http://example.com/x.exe",
            output_root=tmp_path / "output",
        )


def test_generate_winget_manifest_rejects_missing_installer(tmp_path):
    from scripts.generate_winget_manifest import ReleaseInputError, generate_manifest

    with pytest.raises(ReleaseInputError, match="does not exist"):
        generate_manifest(
            version="0.8.0",
            installer=tmp_path / "missing.exe",
            installer_url="https://example.com/x.exe",
            output_root=tmp_path / "output",
        )


def test_generate_winget_manifest_rejects_source_version_mismatch(tmp_path):
    from scripts.generate_winget_manifest import ReleaseInputError, generate_manifest

    installer = tmp_path / "x.exe"
    installer.write_bytes(b"exe")

    with pytest.raises(ReleaseInputError, match="source version"):
        generate_manifest(
            version="0.9.0",
            installer=installer,
            installer_url="https://example.com/x.exe",
            output_root=tmp_path / "output",
        )


def test_release_workflow_builds_first_and_only_publishes_matching_tags():
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )

    assert "workflow_dispatch:" in workflow
    assert "tags:" in workflow
    assert "- \"v*\"" in workflow
    assert "contents: read" in workflow
    assert "contents: write" in workflow
    assert "v$Version" in workflow
    assert "scripts\\build-windows.ps1" in workflow
    assert "generate_winget_manifest.py" in workflow
    assert "winget validate" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "actions/download-artifact@v4" in workflow
    assert "gh release create" in workflow


def test_release_workflow_keeps_manual_runs_from_creating_public_release():
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )

    assert "if: startsWith(github.ref, 'refs/tags/v')" in workflow
    assert "needs: build" in workflow


def test_release_workflow_upgrades_stale_winget_before_validation():
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )

    assert "Install-Module -Name Microsoft.WinGet.Client" in workflow
    assert "Repair-WinGetPackageManager -Force -Latest" in workflow
    assert "-AllUsers" not in workflow
    assert "GITHUB_TOKEN: ${{ github.token }}" in workflow
    assert "if (-not (Get-Command winget" not in workflow


def test_readmes_withhold_winget_commands_until_default_source_is_ready():
    for filename in ("README.md", "README.zh.md"):
        text = (ROOT / filename).read_text(encoding="utf-8")
        assert "winget install --id XuanyuanLuoxue.XCLI -e" not in text
        assert "winget upgrade --id XuanyuanLuoxue.XCLI -e" not in text
        assert "xavier-pen/x-cli" not in text

    english = (ROOT / "README.md").read_text(encoding="utf-8")
    chinese = (ROOT / "README.zh.md").read_text(encoding="utf-8")
    assert "under Microsoft review" in english
    assert "Microsoft 审核" in chinese


def test_release_guide_documents_local_validation_and_external_boundary():
    guide = (ROOT / "docs" / "releasing.md").read_text(encoding="utf-8")

    for expected in (
        "build-windows.ps1",
        "generate_winget_manifest.py",
        "winget validate",
        "microsoft/winget-pkgs",
        "NO_PROXY",
    ):
        assert expected in guide
    assert "不要" in guide and "push" in guide
