"""core/recycle.py — Cross-platform "move to Recycle Bin" support.

v0.5 Phase D implements ``x todo remove`` semantics:
- Default: send the task folder to the system Recycle Bin (recoverable)
- ``--force``: physically delete (permanent)

Why hand-rolled instead of the ``send2trash`` PyPI package?
- AGENTS.md §9 "能少即少" — zero third-party deps for v0.5.
- The three target platforms each have a single, well-known path:

  * **Windows**: ``ctypes`` calls ``SHFileOperationW(FO_DELETE)`` with
    the ``FOF_ALLOWUNDO`` flag → file goes to the Recycle Bin.
  * **macOS**: ``subprocess`` to ``mv <src> ~/.Trash/`` (no native API).
  * **Linux**: ``subprocess`` to ``gio trash <src>`` (modern GLib, the
    XDG Trash spec is universally adopted; fallback to ``.local/share/Trash``
    if ``gio`` is missing — not implemented in v0.5 to keep the surface
    small).

All operations are best-effort: if the platform-specific move fails
(e.g. ``gio`` not on PATH), we return ``False`` and the caller can
fall back to physical deletion (which the caller should already do for
``--force``).

Public API:

* :func:`move_to_recycle_bin` — try to send a single path to the bin
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def move_to_recycle_bin(target: Path) -> bool:
    """Try to send ``target`` to the system Recycle Bin.

    Returns ``True`` on success, ``False`` if the platform-specific
    recycle mechanism is unavailable or fails. The caller is expected
    to handle ``False`` (e.g. by falling back to ``shutil.rmtree``).

    The target must be a single file or directory; multi-target batch
    operations should call this once per target.
    """
    if not target.exists():
        return False  # already gone

    if sys.platform == "win32":
        return _recycle_windows(target)
    if sys.platform == "darwin":
        return _recycle_macos(target)
    # Linux / other Unix
    return _recycle_linux(target)


def _recycle_windows(target: Path) -> bool:
    """Use ctypes + SHFileOperationW with FOF_ALLOWUNDO."""
    try:
        import ctypes
        from ctypes import wintypes

        # SHFileOperationW takes a pointer to a SHFILEOPSTRUCT.
        class SHFILEOPSTRUCT(ctypes.Structure):
            _fields_ = [
                ("hwnd", wintypes.HWND),
                ("wFunc", ctypes.c_uint),
                ("pFrom", ctypes.c_wchar_p),
                ("pTo", ctypes.c_wchar_p),
                ("fFlags", ctypes.c_uint16),
                ("fAnyOperationsAborted", ctypes.c_bool),
                ("hNameMappings", ctypes.c_void_p),
                ("lpszProgressTitle", ctypes.c_wchar_p),
            ]

        FO_DELETE = 0x0003
        FOF_ALLOWUNDO = 0x0040
        FOF_NOCONFIRMATION = 0x0010  # skip "Are you sure?" dialog
        FOF_SILENT = 0x0008

        # pFrom must be a double-null-terminated wide string (one entry).
        from_str = str(target) + "\0\0"

        op = SHFILEOPSTRUCT()
        op.hwnd = None
        op.wFunc = FO_DELETE
        op.pFrom = from_str
        op.pTo = None
        op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT

        shell32 = ctypes.windll.shell32  # type: ignore[attr-defined]
        shell32.SHFileOperationW(ctypes.byref(op))
        # Return code 0 = success; non-zero = aborted/error.
        # We don't strictly check it because Windows sometimes returns
        # non-zero with extended error info but the file did move.
        return not target.exists()
    except Exception:  # noqa: BLE001
        return False


def _recycle_macos(target: Path) -> bool:
    """``mv <src> ~/.Trash/`` — macOS has no public recycle API."""
    trash = Path.home() / ".Trash"
    try:
        trash.mkdir(parents=True, exist_ok=True)
        # If a same-named item already exists in Trash, rename to avoid
        # clobbering (Finder would silently overwrite otherwise).
        dest = trash / target.name
        if dest.exists():
            stem = target.stem
            suffix = target.suffix
            n = 1
            while dest.exists():
                dest = trash / f"{stem} ({n}){suffix}"
                n += 1
        shutil.move(str(target), str(dest))
        return not target.exists()
    except Exception:  # noqa: BLE001
        return False


def _recycle_linux(target: Path) -> bool:
    """``gio trash <src>`` — XDG Trash spec via GLib."""
    try:
        result = subprocess.run(
            ["gio", "trash", str(target)],
            capture_output=True,
            timeout=10,
        )
        if result.returncode == 0 and not target.exists():
            return True
        # Fallback: copy to XDG trash dir directly (without gio)
        trash_dir = Path.home() / ".local" / "share" / "Trash"
        files_dir = trash_dir / "files"
        info_dir = trash_dir / "info"
        if not files_dir.exists():
            return False
        files_dir.mkdir(parents=True, exist_ok=True)
        info_dir.mkdir(parents=True, exist_ok=True)
        dest = files_dir / target.name
        if dest.exists():
            stem = target.stem
            suffix = target.suffix
            n = 1
            while dest.exists():
                dest = files_dir / f"{stem} ({n}){suffix}"
                n += 1
        shutil.move(str(target), str(dest))
        # Write a .trashinfo file (XDG spec, optional but proper)
        info_file = info_dir / (dest.name + ".trashinfo")
        info_file.write_text(
            f"[Trash Info]\nPath={target}\nDeletionDate={__import__('datetime').datetime.now().isoformat()}\n",
            encoding="utf-8",
        )
        return not target.exists()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    except Exception:  # noqa: BLE001
        return False


__all__ = ["move_to_recycle_bin"]