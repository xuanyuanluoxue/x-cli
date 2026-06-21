# 架构设计

> **目标读者**：接续开发 x-cli 的 AI agent 或人类开发者  
> **必读**：**在写代码前必须先读本文档**

---

## 1. 整体架构

### 1.1 设计模式

**微内核架构（Microkernel Architecture）**

```
x (主入口)
├── 插件系统（动态加载）
│   ├── todo（TODO 管理）
│   ├── skill（技能管理，未来）
│   ├── system（系统工具，未来）
│   └── ...（更多插件）
├── 配置管理（~/.xavier/config.yaml）
├── 日志系统（~/.xavier/logs/）
└── 自动更新（未来）
```

**核心思想**：
- **主入口 `x.py`**：只负责解析子命令 + 动态加载插件
- **插件 `plugins/*.py`**：每个功能模块作为独立插件，定义自己的子命令

### 1.2 数据流

```
用户输入: x todo list --status pending
    ↓
主入口解析: subcommand = "todo", args = ["list", "--status", "pending"]
    ↓
动态加载: import plugins.todo
    ↓
调用插件: todo.run(args)
    ↓
执行命令: cmd_list(parsed_args)
    ↓
返回结果: 输出到 stdout / 错误到 stderr
```

---

## 2. 插件机制

### 2.1 插件接口

**每个插件必须定义两个函数**：

```python
# plugins/todo.py

def register(parser):
    """注册子命令到主解析器"""
    subparsers = parser.add_subparsers()
    list_parser = subparsers.add_parser("list")
    list_parser.set_defaults(func=cmd_list)
    # ... 注册更多子命令

def run(args):
    """插件入口：解析参数并路由到对应命令"""
    parser = argparse.ArgumentParser()
    register(parser)
    parsed_args = parser.parse_args(args)
    parsed_args.func(parsed_args)
```

### 2.2 插件加载逻辑

**主入口 `x.py`**：

```python
# x.py
import sys
import importlib

def main():
    if len(sys.argv) < 2:
        print("Usage: x <subcommand> [options]")
        sys.exit(1)
    
    subcommand = sys.argv[1]
    
    try:
        # 动态加载插件
        plugin = importlib.import_module(f"plugins.{subcommand}")
    except ImportError:
        print(f"❌ 错误：未知子命令：{subcommand}")
        sys.exit(1)
    
    # 将剩余参数传给插件
    plugin.run(sys.argv[2:])

if __name__ == "__main__":
    main()
```

### 2.3 插件目录结构

```
plugins/
├── __init__.py       # 必填（Python 包标识）
├── todo.py          # x todo 插件
├── skill.py         # x skill 插件（未来）
└── system.py        # x system 插件（未来）
```

---

## 3. 配置管理

### 3.1 配置文件位置

**全局配置**：`~/.xavier/config.yaml`

```yaml
# ~/.xavier/config.yaml
todo:
  default_status: pending
  default_priority: medium
  tasks_dir: ~/.xavier/TODO/任务

log:
  level: INFO
  file: ~/.xavier/logs/x-cli.log
```

### 3.2 配置加载逻辑

```python
# core/config.py
import yaml
import os

def load_config(config_path=None):
    """加载配置文件"""
    if config_path is None:
        config_path = os.path.expanduser("~/.xavier/config.yaml")
    
    if not os.path.exists(config_path):
        return {}
    
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
```

---

## 4. 数据存储

### 4.1 数据格式

**YAML frontmatter**（兼容现有 TODO 系统）

```markdown
---
id: kemu1
name: 科目一模拟考
status: pending
priority: high
deadline: 2026-08-31
tags: ["驾照", "暑假"]
created: 2026-06-21
updated: 2026-06-21
folder: 任务/科目一
---

# 科目一模拟考

## 笔记

- 需要刷模拟题
- 预约考试日期
```

### 4.2 目录结构

```
~/.xavier/TODO/
├── TODO.md                  # 总索引（自动生成）
├── 00-TODO-SPEC.md       # 规范文档
├── 任务/
│   ├── 科目一/
│   │   └── TODO.md
│   └── 自主实习/
│       └── TODO.md
└── 归档/
    └── 20260615-劳动教育III/
        └── TODO.md
```

---

## 5. 日志系统

### 5.1 日志配置

**日志级别**（从低到高）：
- `DEBUG`: 调试信息（开发时用）
- `INFO`: 一般信息（默认）
- `WARNING`: 警告信息
- `ERROR`: 错误信息

**日志输出**：
- 控制台：≥ `WARNING`（只显示错误和警告）
- 文件：`~/.xavier/logs/x-cli.log`（≥ `INFO`）

### 5.2 日志格式

```
2026-06-21 03:10:23 [INFO] x.todo.add: 任务已创建：kemu1
2026-06-21 03:10:24 [ERROR] x.todo.update: 任务不存在：kemu99
```

---

## 6. 错误处理

### 6.1 退出码

| 退出码 | 含义 |
|--------|------|
| 0 | 成功 |
| 1 | 通用错误（如：任务不存在）|
| 2 | 命令行参数错误（如：缺少必填参数）|

### 6.2 错误消息格式

**成功**：
```
✅ 任务已创建：科目一模拟考（ID: kemu1）
```

**错误**：
```
❌ 错误：任务名已存在：科目一模拟考（ID: kemu1）
```

**用法错误**（退出码 2）：
```
❌ 错误：缺少必填参数 <任务名称>

用法：x todo add <名称> [选项]

选项：
  --priority <优先级>    优先级（high/medium/low）
  --deadline <日期>      截止日期（YYYY-MM-DD）
  --tags <标签>          标签（逗号分隔）
```

---

## 7. 测试策略

### 7.1 测试层次

| 层次 | 工具 | 覆盖目标 |
|------|------|----------|
| **单元测试** | `pytest` | 核心逻辑（`core/` 模块）|
| **集成测试** | `pytest` + `tempfile` | 插件与核心的交互 |
| **行为测试** | `pytest` + BDD 规格 | 用户场景（Given-When-Then）|
| **端到端测试** | `subprocess` | 完整命令行流程 |

### 7.2 测试覆盖率目标

- **核心逻辑**（`core/`）：≥ 90%
- **插件代码**（`plugins/`）：≥ 80%
- **全局**：≥ 80%

---

## 8. 打包与发布

### 8.1 PyInstaller 打包

**命令**：
```bash
pyinstaller --onefile --name x x.py
```

**产物**：
- Windows: `dist/x.exe`（~10 MB）
- macOS: `dist/x`（~10 MB）
- Linux: `dist/x`（~10 MB）

### 8.2 GitHub Release

**自动化**（GitHub Actions）：
1. 打 tag（`v1.0.0`）
2. 自动运行测试（`pytest`）
3. 自动打包（PyInstaller）
4. 自动创建 Release（上传二进制）

---

## 9. 未来扩展

### 9.1 插件市场（可选）

** idea**：允许用户分享自定义插件（`x plugin install <名称>`）

**实现方式**：
- 插件仓库（GitHub）
- 插件元数据（`plugin.yaml`）
- 自动下载 + 安装

### 9.2 交互式 TUI（可选）

**idea**：用 `rich` 库实现终端 UI

**示例**：
```
┌─────────────────────────────────────┐
│  x todo tui                       │
├─────────────────────────────────────┤
│  ID    Name                Status   │
│  kemu1 科目一模拟考         pending  │
│  kemu2 自主实习材料         in_prog │
│  ...                                 │
└─────────────────────────────────────┘
```

### 9.3 Git 自动提交（可选）

**idea**：每次 `x todo add/update` 自动 `git commit`

**实现方式**：
- 检测 `~/.xavier/TODO/` 是否是 Git 仓库
- 如果是，自动提交（提交信息由 AI 生成）

---

*本文档是活文档，随架构演进更新*
