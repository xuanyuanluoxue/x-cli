r"""Build a standalone executable for x-cli.

This script wraps `PyInstaller <https://pyinstaller.org/>`_ to package
``x.py`` as a single-file binary (``x`` on Unix, ``x.exe`` on Windows)
under the platform-appropriate :func:`xcli_data_dir` (so the binary
lives next to the config / logs / secrets without polluting the repo).

Why a wrapper instead of running ``pyinstaller`` directly?
========================================================

Three reasons:

1. **Cross-platform output path**. We respect the v0.5+ layout
   ``<xcli_data_dir>/bin/x{.exe}`` instead of dumping artefacts into
   ``dist/`` next to the source tree. This keeps the repo clean and
   makes the binary discoverable next to other x-cli state.

2. **Reusable from CI**. This script takes a ``--platform`` flag so a
   single CI definition can build for win/mac/linux on the matching
   runner (PyInstaller cannot cross-compile, so each build runs on its
   native OS).

3. **Self-checked prerequisites**. The script verifies that
   ``pyinstaller`` is importable (via ``shutil.which``) and that the
   source entry point exists, with friendly error messages rather than
   a raw ``ModuleNotFoundError`` deep inside PyInstaller.

Usage
-----

    # 1. Install PyInstaller into the project venv (one-time)
    .venv\Scripts\python.exe -m pip install pyinstaller

    # 2. Build (current platform, default)
    .venv\Scripts\python.exe release\build.py

    # 3. Build with a clean ``build/`` and ``dist/`` cache
    .venv\Scripts\python.exe release\build.py --clean

    # 4. Build for a specific target platform (hint only; PyInstaller
    #    can only build on the OS it runs on, so this is documentation)
    .venv\Scripts\python.exe release\build.py --platform linux

Output
------

* Binary: ``<xcli_data_dir>/bin/x`` (POSIX) or ``<xcli_data_dir>/bin/x.exe`` (Windows)
* Work cache: ``<repo>/build/``  (gitignored, safe to ``--clean``)
* Spec file: ``<repo>/build/x.spec``  (regenerated each build)

Limitations
-----------

* PyInstaller is **not** cross-platform. To build a Windows binary you
  must run this script on Windows (or under WSL with caveats). The
  ``--platform`` flag is a build-time hint, not a cross-compile switch.
* No code signing / notarisation. This is for personal use only.
* Antivirus on Windows may flag the bundled ``x.exe`` (PyInstaller
  artefacts trigger false positives). Add an exclusion or sign the
  binary if you need to ship to others.

Dependencies
------------

PyInstaller is the only third-party dependency. It is **not** declared
in ``pyproject.toml`` because x-cli's runtime stays stdlib-only — the
build step is opt-in and only needed when producing a binary.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

# --- Paths -------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
ENTRY = ROOT / "x.py"


def xcli_data_dir() -> Path:
    """Cross-platform x-cli data directory (mirrors ``core.paths.xcli_data_dir``).

    Duplicated here to keep ``release/`` standalone — importing from
    ``core.paths`` would pull in the full x-cli module graph (which is
    not a build dependency). Behaviour matches ``core.paths`` v0.5+:
    Windows → ``%LOCALAPPDATA%\\x-cli``, Unix → ``$XDG_DATA_HOME/x-cli``
    (defaulting to ``~/.local/share/x-cli``).
    """
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
        if not base:
            # Should not happen on Win10+, but be defensive
            base = str(Path.home() / "AppData" / "Local")
        return Path(base) / "x-cli"
    # POSIX (Linux + macOS)
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / "x-cli"


# --- Pre-flight checks -------------------------------------------------------


def check_pyinstaller() -> str:
    """Return the path to the ``pyinstaller`` binary, or exit with a helpful
    error if it is not installed.
    """
    pyinstaller_bin = shutil.which("pyinstaller")
    if pyinstaller_bin is None:
        print(
            "❌ PyInstaller 未安装。\n"
            "   在项目 venv 中跑：\n"
            r"       .venv\Scripts\python.exe -m pip install pyinstaller"
            "\n"
            "   （Unix 上：.venv/bin/python -m pip install pyinstaller）",
            file=sys.stderr,
        )
        sys.exit(2)
    return pyinstaller_bin


def check_entry() -> None:
    """Verify ``x.py`` exists at the expected path."""
    if not ENTRY.is_file():
        print(f"❌ 找不到入口文件：{ENTRY}", file=sys.stderr)
        sys.exit(2)


# --- Build -------------------------------------------------------------------


def clean_cache(force: bool) -> None:
    """Remove ``build/`` and ``dist/`` (under the repo root) if ``--clean``."""
    if not force:
        return
    for sub in ("build", "dist"):
        path = ROOT / sub
        if path.exists():
            print(f"→ 清理 {path.relative_to(ROOT)}/")
            shutil.rmtree(path)


def run_pyinstaller(pyinstaller_bin: str, output_dir: Path) -> int:
    """Invoke ``pyinstaller`` with the flags we want and stream output.

    Returns the exit code from the subprocess.
    """
    work_dir = ROOT / "build"
    work_dir.mkdir(parents=True, exist_ok=True)

    exe_name = "x.exe" if os.name == "nt" else "x"
    cmd = [
        pyinstaller_bin,
        "--onefile",
        "--name", "x",
        "--distpath", str(output_dir),
        "--workpath", str(work_dir),
        "--specpath", str(work_dir),
        "--clean",
        "--noconfirm",
        # Quiet down PyInstaller's INFO logs; show only WARN+ to stderr.
        # Uncomment for verbose debugging:
        # "--log-level", "DEBUG",
        str(ENTRY),
    ]
    print("→ PyInstaller 调起：")
    print("  " + " ".join(cmd))
    print()
    # Stream stdout/stderr through unchanged so the user sees the
    # bundling progress in real time.
    return subprocess.call(cmd, cwd=str(ROOT))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="release/build.py",
        description=(
            "把 x-cli 打包成单文件可执行（x 或 x.exe），输出到 "
            "<xcli_data_dir>/bin/ 下。详情见 docstring。"
        ),
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="先清理仓库下的 build/ 和 dist/ 缓存（默认保留）。",
    )
    parser.add_argument(
        "--platform",
        choices=("current", "win", "mac", "linux"),
        default="current",
        help=(
            "目标平台提示（PyInstaller 不支持交叉编译 —— 实际只能在"
            "目标 OS 上跑这个脚本构建。默认 current = 当前 OS）。"
        ),
    )
    args = parser.parse_args(argv)

    check_entry()
    pyinstaller_bin = check_pyinstaller()

    if args.platform != "current" and args.platform != _current_platform_key():
        print(
            f"⚠️  提示：你在 {args.platform!r} 目标上跑，但当前 OS 是 "
            f"{_current_platform_key()!r}。PyInstaller 不支持交叉编译 —— "
            "请在目标 OS 上重跑。",
            file=sys.stderr,
        )

    output_dir = xcli_data_dir() / "bin"
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"→ 输出目录：{output_dir}")

    clean_cache(args.clean)
    rc = run_pyinstaller(pyinstaller_bin, output_dir)

    if rc != 0:
        print(f"\n❌ PyInstaller 失败（exit {rc}）", file=sys.stderr)
        return rc

    exe_name = "x.exe" if os.name == "nt" else "x"
    final = output_dir / exe_name
    if not final.is_file():
        print(
            f"\n❌ 找不到预期产物：{final}\n"
            "   PyInstaller 报告成功但没产出文件 —— 检查上方日志。",
            file=sys.stderr,
        )
        return 1

    size_mb = final.stat().st_size / (1024 * 1024)
    print(
        f"\n✅ 构建完成：{final}  ({size_mb:.1f} MB)\n"
        f"   测试：{final} --version"
    )
    return 0


def _current_platform_key() -> str:
    """Return ``win`` / ``mac`` / ``linux`` for the current OS."""
    if os.name == "nt":
        return "win"
    if sys.platform == "darwin":
        return "mac"
    return "linux"


if __name__ == "__main__":
    sys.exit(main())
