# x note P0 行为规格

> **目标读者**：接续开发的 AI agent / 维护者
>
> **范围**：`x note add/list/show/search`
>
> **对应测试**：`tests/test_note.py`
>
> **状态**：P0

---

## 1. 产品边界

- `x diary` 是按自然日追加的时间流记录。
- `x note` 是按主题独立保存、可再次查找的长期笔记。
- P0 不提供编辑、删除、归档、双链、附件或同步。

## 2. 存储约定

### 2.1 路径

| 平台 | 默认目录 |
|---|---|
| Windows | `%LOCALAPPDATA%\x-cli\notes\` |
| macOS / Linux | `$XDG_DATA_HOME/x-cli/notes/`，未设置时为 `~/.local/share/x-cli/notes/` |

- `XCLI_NOTES_DIR` 可覆盖整个笔记目录。
- 目录在首次解析路径或创建 `NoteStore` 时自动创建。
- 每篇笔记保存为 `<id>.md`；其他扩展名忽略。

### 2.2 ID 与 Markdown

ID 使用创建时的本地时间：`n-YYYYMMDD-HHMMSS`。同一秒创建多篇时依次使用 `-2`、`-3`。

```markdown
---
id: n-20260717-143012
title: MiniMax API 配置
tags: [AI, API]
created_at: 2026-07-17T14:30:12
updated_at: 2026-07-17T14:30:12
---

这里是正文。
```

- 文件名必须等于 frontmatter 的 `id`。
- `title` 必填且去除首尾空白；`body` 可为空。
- tags 来自英文逗号分隔输入，去除首尾空白和空项，并按首次出现顺序去重。
- `created_at` / `updated_at` 使用本地时间、精确到秒的 ISO 8601 格式。

---

## 3. 行为场景

### 场景 1：add 创建主题笔记

**When**：

```text
x note add "MiniMax API 配置" --body "这里是正文。" --tags "AI,API"
```

**Then**：

- 退出码为 `0`。
- 创建符合第 2.2 节格式的 Markdown 文件。
- stdout 输出 `✅ 笔记已创建：MiniMax API 配置（ID: <id>）`。

### 场景 2：同秒 ID 冲突

**Given**：`n-20260717-143012.md` 已存在。

**When**：同一秒再创建两篇笔记。

**Then**：新 ID 依次为 `n-20260717-143012-2` 和 `n-20260717-143012-3`，不覆盖已有文件。

### 场景 3：拒绝空标题

**When**：标题为空字符串或只含空白。

**Then**：

- 退出码为 `2`。
- stderr 输出 `❌ 笔记标题不能为空`。
- 不创建文件。

### 场景 4：list 默认列出最近 20 篇

**When**：执行 `x note list`。

**Then**：

- 退出码为 `0`。
- 输出列为 `ID / Title / Tags / Updated` 的 CJK 对齐表格。
- 按 `updated_at` 从新到旧排序，相同时间按 ID 降序。
- 最多输出 20 篇。

### 场景 5：list 按标签过滤

**When**：执行 `x note list --tag AI --limit 3`。

**Then**：

- tag 使用不区分大小写的完整值匹配。
- 只显示匹配的最近 3 篇。
- `--limit` 必须是正整数。

### 场景 6：空笔记库

**When**：空目录执行 `x note list` 或无匹配结果。

**Then**：stdout 只输出 `📭 暂无笔记`，退出码为 `0`。

### 场景 7：show 显示一篇笔记

**When**：执行 `x note show n-20260717-143012`。

**Then**：stdout 依次显示标题、ID、Tags、Created、Updated 和正文，退出码为 `0`。

### 场景 8：show 不存在

**When**：执行 `x note show n-missing`。

**Then**：stderr 输出 `❌ 笔记不存在：n-missing`，退出码为 `3`，stdout 为空。

### 场景 9：search 跨字段搜索

**When**：执行 `x note search minimax --limit 5`。

**Then**：

- 在 title、tags、body 中做不区分大小写的子串匹配。
- 输出格式和排序与 list 相同，最多 5 篇。
- 空关键词或纯空白关键词返回退出码 `2`，不读取文件。

### 场景 10：非法 limit

**When**：`list/search --limit` 为 `0`、负数或非整数。

**Then**：argparse 返回退出码 `2`，不读取或修改文件。

### 场景 11：损坏的笔记文件

**Given**：notes 目录存在缺少 frontmatter、必填字段、时间字段非法或文件名与 ID 不一致的 `.md` 文件。

**When**：执行 list 或 search。

**Then**：stderr 输出 `❌ 笔记数据损坏：<文件名>（<原因>）`，退出码为 `5`，不输出部分结果。

### 场景 12：帮助和入口派发

**When**：执行 `x note --help`。

**Then**：

- 退出码为 `0`。
- stdout 包含 `usage: x note` 和 `add / list / show / search`。
- 顶层 `x --help` 的子命令提示包含 `note`。

---

## 4. 退出码

| 退出码 | 含义 |
|---|---|
| 0 | 成功，包括空列表 |
| 2 | 参数错误、空标题、空搜索词 |
| 3 | 指定 ID 不存在 |
| 5 | Markdown/frontmatter 数据损坏或读取失败 |

## 5. 不变量

- 只使用 Python 标准库和项目已有 core 模块。
- 不触碰 Obsidian、Xavier 日记或其他笔记目录。
- add 使用独占创建语义，永不覆盖已有笔记。
