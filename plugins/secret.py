"""plugins/secret.py — ``x secret`` subcommand plugin (Phase 4 split).

8 subcommands: list / get / set / update / rm / search / import / export.
See :mod:`x` for the dispatch glue.

Plugin contract (required by ``x.py``):

* :func:`register` — bind subparsers + flags for all actions
* :func:`run` — parse ``sys.argv[1:]`` for this subcommand and dispatch
  to the right handler

Per-subcommand BDD spec: :mod:`docs.behaviors.secret`.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Callable, Sequence

from core.formatting import display_width, pad


# ============================================================
#  Plugin contract: register() + run()
# ============================================================


SECRET_ACTIONS: tuple[str, ...] = (
    "list",
    "get",
    "set",
    "update",
    "rm",
    "search",
    "import",
    "export",
)


def register(parser: argparse.ArgumentParser) -> None:
    """注册 x secret 的子命令参数。

    对应 BDD：``docs/behaviors/secret-behavior.md``（17 个场景）。

    子命令：list / get / set / update / rm / search / import / export。
    所有 core.secrets / core.paths 调用都在 handler 内做 lazy import，
    保证 x.py 顶层 import 始终成功（core.secrets 正在并行实现）。
    """
    sub = parser.add_subparsers(
        dest="secret_action", required=False, metavar="ACTION"
    )

    # list — 无参数
    sub.add_parser("list", help="列出所有密钥（不显示 value）")

    # get <name> [--full]
    sp = sub.add_parser("get", help="取一个 value（默认复制到剪贴板 + 输出到 stdout）")
    sp.add_argument("name", help="密钥名（精确 / 模糊匹配）")
    sp.add_argument(
        "--full",
        action="store_true",
        help="显示完整元数据表格（跳过剪贴板 / 跳过 stdout）",
    )
    sp.add_argument(
        "--no-clipboard",
        action="store_true",
        help="不复制到剪贴板（仅 stdout）",
    )
    sp.add_argument(
        "--no-stdout",
        action="store_true",
        help="不输出到 stdout（仅剪贴板，适合\"用完即弃\"的场景）",
    )

    # set <name> --value <v> [--category <c>] [--note <n>]
    sp = sub.add_parser("set", help="新增条目")
    sp.add_argument("name", help="密钥名（唯一）")
    sp.add_argument("--value", required=True, help="密钥值")
    sp.add_argument(
        "--category", default="default", help="分类（默认 default）"
    )
    sp.add_argument("--note", default="", help="备注")

    # update <name> [--value <v>] [--note <n>]
    sp = sub.add_parser("update", help="修改 value / note")
    sp.add_argument("name", help="密钥名")
    sp.add_argument("--value", help="新 value（不传则不改）")
    sp.add_argument(
        "--note",
        help="新 note（不传则不改；传空字符串会清空）",
    )

    # rm <name>
    sp = sub.add_parser("rm", help="删除条目")
    sp.add_argument("name", help="密钥名")

    # search <keyword>
    sp = sub.add_parser("search", help="按 name/note 模糊搜（不搜 value）")
    sp.add_argument("keyword", help="关键词")

    # import --from <dir>
    sp = sub.add_parser("import", help="从 .md 批量迁移")
    sp.add_argument(
        "--from",
        dest="src_dir",
        required=True,
        help="源目录（含 .md 文件）",
    )

    # export [--to <path>]
    sp = sub.add_parser("export", help="JSON 备份")
    sp.add_argument(
        "--to",
        dest="dest",
        help=(
            "备份文件路径（默认 <db_dir>/secrets-backup-YYYYMMDD-HHMMSS.json）"
        ),
    )


def run(args: Sequence[str]) -> int:
    """x secret 入口：解析参数并分发到子命令 handler。

    对应 BDD：``docs/behaviors/secret-behavior.md``（17 场景）。

    无 action → 打印 usage + 退出码 0（BDD §场景 16）。
    action 解析后通过 ``globals().get("_secret_<action>")`` 派发到对应 handler。
    """
    parser = argparse.ArgumentParser(
        prog="x secret", description="密钥管理（独立 JSON DB）"
    )
    register(parser)
    parsed = parser.parse_args(list(args))

    if not parsed.secret_action:
        parser.print_help()
        return 0

    handler_name = f"_secret_{parsed.secret_action.replace('-', '_')}"
    handler = globals().get(handler_name)
    if handler is None:
        print(
            f"🚧 x secret {parsed.secret_action} 还未实现",
            file=sys.stderr,
        )
        return 1
    return handler(parsed)


# ============================================================
#  Table renderer (shared by list / search)
# ============================================================


# list / search 共用的表格列定义（表头 + 取值函数），集中维护 schema
_SECRET_LIST_COLUMNS: tuple[tuple[str, Callable[[object], str]], ...] = (
    ("Name", lambda e: f"🔐 {e.name}"),
    ("Category", lambda e: f"📂 {e.category}"),
    ("Updated", lambda e: f"🕐 {e.updated_at}"),
)


def _render_secret_table(entries: list) -> str:
    """Render a list of SecretEntry as a CJK-aligned table (BDD §场景 1, 12).

    空列表走友好提示行，不打表头。列宽按表头与所有数据行的最大
    display-width 计算（CJK 按 2 宽算），保证中英混排对齐。
    """
    if not entries:
        return "📭 暂无密钥（试试 x secret set <name> --value <v> 创建）\n"

    header_cells = [h for h, _ in _SECRET_LIST_COLUMNS]
    rows: list[list[str]] = [
        [col(e) for _, col in _SECRET_LIST_COLUMNS] for e in entries
    ]
    col_widths = [
        max(
            [display_width(header_cells[i])]
            + [display_width(row[i]) for row in rows]
        )
        for i in range(len(_SECRET_LIST_COLUMNS))
    ]

    lines: list[str] = [
        "  ".join(pad(c, col_widths[i]) for i, c in enumerate(header_cells)),
        "  ".join("─" * col_widths[i] for i in range(len(_SECRET_LIST_COLUMNS))),
    ]
    for row in rows:
        lines.append(
            "  ".join(pad(c, col_widths[i]) for i, c in enumerate(row))
        )
    return "\n".join(lines) + "\n"


# ============================================================
#  Handlers
# ============================================================


def _secret_list(args: argparse.Namespace) -> int:
    """``x secret list`` — 列出所有密钥（不显示 value）。

    对应 BDD：§场景 1。按 name 字典序升序，永不显示 value（硬性约束）。
    退出码 0（包含空仓库）。
    """
    from core.secrets import SecretStore  # lazy import

    store = SecretStore()
    entries = sorted(store.list(), key=lambda e: e.name)
    sys.stdout.write(_render_secret_table(entries))
    return 0


def _secret_get(args: argparse.Namespace) -> int:
    """``x secret get <name> [--full] [--no-clipboard] [--no-stdout]`` — 取一个 value。

    对应 BDD：§场景 2-4 + 用户增强（剪贴板）。

    默认行为（最常用 — 拿来即用）:
      - stdout 输出 value（兼容管道 / 旧测试）
      - 复制 value 到系统剪贴板（按量使用的核心场景：拿到就粘贴）
      - stderr 永远打警告

    退出码：0 成功 / 3 找不到。
    """
    from core.secrets import SecretStore  # lazy import

    store = SecretStore()
    entry = store.find(args.name)
    if entry is None:
        print(f"❌ 密钥不存在：{args.name}", file=sys.stderr)
        return 3

    if args.full:
        # 完整元数据表格（BDD §场景 3）— 不复制到剪贴板（剪贴板只放纯值）
        rows: list[tuple[str, str]] = [
            ("name", entry.name),
            ("category", entry.category),
            ("value", entry.value),
            ("note", entry.note or ""),
            ("created_at", entry.created_at),
            ("updated_at", entry.updated_at),
        ]
        col0_w = max(
            display_width("Field"),
            max(display_width(r[0]) for r in rows),
        )
        col1_w = max(
            display_width("Value"),
            max(display_width(r[1]) for r in rows),
        )
        out: list[str] = [
            "  ".join([pad("Field", col0_w), pad("Value", col1_w)]),
            "  ".join(["─" * col0_w, "─" * col1_w]),
        ]
        for k, v in rows:
            out.append("  ".join([pad(k, col0_w), pad(v, col1_w)]))
        sys.stdout.write("\n".join(out) + "\n")
        return 0

    # 默认流程：stdout + 剪贴板
    if not args.no_stdout:
        print(entry.value)

    if not args.no_clipboard:
        ok, msg = _copy_to_clipboard(entry.value)
        if ok:
            print(f"📋 已复制到剪贴板（{msg}）", file=sys.stderr)
        else:
            print(f"⚠️ 复制到剪贴板失败：{msg}（请用 --no-stdout 关掉 stdout 或手动复制）", file=sys.stderr)

    # BDD 硬性约束：get 永远 stderr 警告（不管是否 tty / 是否有 --full）
    print(
        "🔐 警告：密钥已输出到 stdout（可能被 shell 历史 / 日志捕获）",
        file=sys.stderr,
    )
    return 0


def _copy_to_clipboard(text: str) -> tuple[bool, str]:
    """Copy ``text`` to the system clipboard. Returns ``(success, backend_name)``.

    Tries in order: ``clip.exe`` (Windows) → ``pbcopy`` (macOS) → ``xclip`` (Linux X11)
    → ``wl-copy`` (Linux Wayland) → fall back to printing a hint.

    Stdlib only (no ``pyperclip``).
    """
    encoded = text.encode("utf-8")
    candidates: list[tuple[list[str], str]] = [
        (["clip"], "Windows clip.exe"),
        (["pbcopy"], "macOS pbcopy"),
        (["xclip", "-selection", "clipboard"], "Linux xclip"),
        (["wl-copy"], "Linux wl-copy (Wayland)"),
    ]
    for cmd, name in candidates:
        try:
            subprocess.run(
                cmd,
                input=encoded,
                check=True,
                timeout=5,
                capture_output=True,
            )
            return True, name
        except FileNotFoundError:
            continue
        except subprocess.TimeoutExpired:
            return False, f"{name} 超时"
        except subprocess.CalledProcessError as e:
            return False, f"{name} 退出码 {e.returncode}"
    return False, "未找到剪贴板后端（clip/pbcopy/xclip/wl-copy）"


def _secret_set(args: argparse.Namespace) -> int:
    """``x secret set <name> --value <v> [--category <c>] [--note <n>]`` — 新增条目。

    对应 BDD：§场景 5-7。已存在 → 退出码 4（用 update 改）。
    """
    from core.secrets import SecretAlreadyExistsError, SecretStore  # lazy import

    store = SecretStore()
    try:
        entry = store.set(
            args.name,
            args.value,
            category=args.category,
            note=args.note,
        )
    except SecretAlreadyExistsError:
        print(
            f"❌ 密钥已存在：{args.name}（用 x secret update 修改）",
            file=sys.stderr,
        )
        return 4

    print(f"✅ 密钥已创建：{entry.name}")
    return 0


def _secret_update(args: argparse.Namespace) -> int:
    """``x secret update <name> [--value <v>] [--note <n>]`` — 修改 value / note。

    对应 BDD：§场景 8-9。
    - 至少要指定 ``--value`` 或 ``--note`` 之一（否则退码 2）
    - ``--note ""`` 显式传空串表示清空 note
    - 找不到 → 退出码 3
    """
    if args.value is None and args.note is None:
        print(
            "❌ 至少要指定 --value 或 --note 之一",
            file=sys.stderr,
        )
        return 2

    from core.secrets import SecretNotFoundError, SecretStore  # lazy import

    store = SecretStore()
    try:
        entry = store.update(args.name, value=args.value, note=args.note)
    except SecretNotFoundError:
        print(f"❌ 密钥不存在：{args.name}", file=sys.stderr)
        return 3

    print(f"✅ 密钥已更新：{entry.name}")
    return 0


def _secret_rm(args: argparse.Namespace) -> int:
    """``x secret rm <name>`` — 删除条目。

    对应 BDD：§场景 10-11。找不到 → 退出码 3。
    """
    from core.secrets import SecretNotFoundError, SecretStore  # lazy import

    store = SecretStore()
    try:
        entry = store.rm(args.name)
    except SecretNotFoundError:
        print(f"❌ 密钥不存在：{args.name}", file=sys.stderr)
        return 3

    print(f"✅ 密钥已删除：{entry.name}")
    return 0


def _secret_search(args: argparse.Namespace) -> int:
    """``x secret search <keyword>`` — 按 name/note 模糊搜（不搜 value）。

    对应 BDD：§场景 12。搜索范围 = name + note，硬性**不**搜 value
    （避免 grep 撞到密钥）。输出格式与 list 一致。
    """
    from core.secrets import SecretStore  # lazy import

    store = SecretStore()
    entries = sorted(store.search(args.keyword), key=lambda e: e.name)
    sys.stdout.write(_render_secret_table(entries))
    return 0


def _secret_import(args: argparse.Namespace) -> int:
    """``x secret import --from <dir>`` — 从 .md 批量迁移。

    对应 BDD：§场景 13-14。源目录不存在 → 退出码 5。
    旧 .md 文件**保留**（单向导入，不删源文件）。
    """
    from core.secrets import SecretStore  # lazy import

    src = Path(args.src_dir)
    if not src.is_dir():
        print(f"❌ 源目录不存在：{src}", file=sys.stderr)
        return 5

    store = SecretStore()
    imported, skipped = store.import_from_dir(src)
    print(f"📥 迁移完成：导入 {imported} 条，跳过 {skipped} 条（重复）")
    return 0


def _secret_export(args: argparse.Namespace) -> int:
    """``x secret export [--to <path>]`` — JSON 备份。

    对应 BDD：§场景 15。默认路径 = ``<db_dir>/secrets-backup-YYYYMMDD-HHMMSS.json``。
    """
    from core.secrets import SecretStore  # lazy import

    dest = Path(args.dest) if args.dest else None
    store = SecretStore()
    path = store.export(dest)
    n = len(store.list())
    print(f"✅ 已备份 {n} 条到 {path}")
    return 0