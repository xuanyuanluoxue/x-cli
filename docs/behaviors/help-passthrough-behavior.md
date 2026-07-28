# help 命令 & --help passthrough 行为规格

> v0.6.1 — 修复 COMMANDS.md P2：`--help` 解析修复（现在被顶层 parser 截走，没传给子命令）

## 场景 1: `x help`（顶层 help 别名）

**Given**：
- `x` 命令已安装

**When**：
- 用户执行 `x help`

**Then**：
- exit code = 0
- stdout 输出顶层 help（包含 `usage: x` / `SUBCOMMAND` / `--config` / `--log-level` 等）
- stderr 为空
- 行为与 `x --help` 完全一致

## 场景 2: `x todo --help`（子命令 --help passthrough）

**Given**：
- `x todo` 子命令已注册

**When**：
- 用户执行 `x todo --help`

**Then**：
- exit code = 0
- stdout 输出 **`x todo` 自己的 help**（不是顶层 help）
- 包含 `todo_action` 子动作列表：`list` / `add` / `update` / `archive` / `restore` / `search` / `done` / `stats` / `init` / `import` 等

## 场景 3: `x todo -h`（子命令短选项 --help）

**Given**：
- `x todo` 子命令已注册

**When**：
- 用户执行 `x todo -h`

**Then**：
- exit code = 0
- stdout 输出 `x todo` 自己的 help
- 与场景 2 等价

## 场景 4: `x secret --help`

**Given**：
- `x secret` 子命令已注册

**When**：
- 用户执行 `x secret --help`

**Then**：
- exit code = 0
- stdout 输出 **`x secret` 自己的 help**（不是顶层 help）
- 包含 secret action：`list` / `get` / `set` / `update` / `rm` / `search` / `import` / `export`

## 场景 5: `x web --help`

**Given**：
- `x web` 子命令已注册

**When**：
- 用户执行 `x web --help`

**Then**：
- exit code = 0
- stdout 输出 **`x web` 自己的 help**（不是顶层 help）
- 包含 web 子命令 flag：`--host` / `--port` / `--token` / `--no-browser` / `--auto-token-url`

## 场景 6: `x todo help`（子命令位置参数 help 别名）

**Given**：
- `x todo` 子命令已注册

**When**：
- 用户执行 `x todo help`（位置参数 `help`，不是 `--help` flag）

**Then**：
- exit code = 0
- stdout 输出 `x todo` 自己的 help
- 与场景 2 / 3 等价

---

## 设计说明

**问题根因**：`x.py:build_parser()` 用 `argparse.ArgumentParser(...)` 默认 `add_help=True`，导致 argparse 在 `parse_known_args()` 看到 `--help` 时**直接截走并 sys.exit(0)**，`remaining` 不会包含 `--help`，子命令 handler 永远收不到。

**修复要点**：
1. `x.py:build_parser()` 加 `add_help=False`，手动加 `-h/--help` flag
2. `x.py:main()` 显式处理 `parsed.help` 和 `parsed.subcommand == "help"` 两种顶层 help 入口
3. 三个 plugin 的 `run()` 在调用 `parser.parse_args(argv)` 之前短路 `argv == ["help"]` → `parser.print_help() + return 0`