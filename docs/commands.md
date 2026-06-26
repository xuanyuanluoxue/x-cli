# 命令参考

> **目标读者**：使用 x-cli 的人类（包括未来的你）
> **说明**：本文档列出所有命令的完整参考
> **状态**：v0.2.0 MVP 实际实现（2026-06-21）

---

## 1. 总入口：`x`

### 1.1 用法

```bash
x <子命令> [选项]
```

### 1.2 全局选项

| 选项 | 状态 | 说明 |
|------|------|------|
| `-v, --version` | ✅ 已实现 | 显示版本号（v0.2.0）|
| `-h, --help` | ✅ 已实现 | 显示帮助（argparse 默认）|
| `--config <路径>` | ❌ 未实现 | 指定配置文件（计划读取 `<xcli_config_path>`）|
| `--log-level <级别>` | ❌ 未实现 | 设置日志级别（DEBUG/INFO/WARNING/ERROR）|

### 1.3 环境变量

| 变量 | 状态 | 说明 |
|------|------|------|
| `XCLI_TODO_DIR` | ✅ 已实现 | 覆盖 TODO 根目录（默认 `<legacy-config-dir>/TODO`）。主要给测试用 |

### 1.4 示例

```bash
# 显示版本号
x --version
# 输出: x 0.2.0

# 显示帮助
x --help
x todo --help
x todo add --help

# 切数据源（测试用）
XCLI_TODO_DIR=/tmp/test python x.py todo list
```

---

## 2. `x todo` — TODO 管理

### 2.1 子命令概览

| 子命令 | 状态 | 说明 | 参数 |
|--------|------|------|------|
| `x todo list` | ✅ | 列出任务 | `--status` / `--priority` / `--tag` / `--all` |
| `x todo add <名称>` | ✅ | 添加任务 | `--priority` / `--deadline` / `--tags` |
| `x todo update <id>` | ✅ | 更新任务 | `--status` / `--priority` / `--deadline` / `--tags` |
| `x todo archive <id>` | ✅ | 归档任务 | `--reason` |
| `x todo stats` | ✅ | 统计信息 | 无 |
| `x todo search <keyword>` | ✅ | 跨字段模糊搜索 | `--active-only` / `--archived-only` / `--status` |
| `x todo init` | ❌ | 初始化 TODO 目录 | — |
| `x todo restore` | ❌ | 从归档还原 | — |

---

### 2.2 `x todo list` — 列出任务

**用法**：
```bash
x todo list [选项]
```

**选项**：

| 选项 | 说明 |
|------|------|
| `--status <状态>` | 按状态过滤（pending / in_progress / blocked / waiting / archived）|
| `--priority <优先级>` | 按优先级过滤（high / medium / low）|
| `--tag <标签>` | 按标签过滤（精确匹配 `tags` 列表中的任一元素）|
| `--all` | 显示所有任务（含已归档）|

> **默认行为**：不显示已归档任务；想看归档加 `--all` 或 `--status archived`

**示例**：
```bash
# 列出所有活动任务
x todo list

# 列出进行中的
x todo list --status in_progress

# 列出高优先级
x todo list --priority high

# 组合过滤（AND 关系）
x todo list --priority high --tag 驾照

# 含已归档
x todo list --all
```

**输出格式**（tab 分隔）：
```
ID                      Name              Status       Priority    Deadline
zhuxuejin-2026xia       助学金-下学期材料  in_progress  high        2026-06-22
zizhu-shixi             自主实习          in_progress  high        2026-07-01
kemu1                   驾驶证考取        pending      high        2026-08-31
zimeiti-geren-ip        自媒体-个人IP      pending      medium      -
```

> 归档任务的 Status 列会附 reason：`archived (done)`

**自动归档（opt-in）**：

当配置文件 `<xcli_data_dir>/config.yaml` 设 `todo.auto_archive: true`，或环境变量 `XCLI_TODO_AUTO_ARCHIVE=1`（非零非空字符串）时，本命令进入时会**先**扫描活动任务，自动归档 `deadline < today()` 的任务（`reason=expired`），再输出表格。

- stdout **顶部**打印一行摘要：`⏰ 自动归档 N 个逾期任务：id1 / id2 / ...`
- 0 个逾期任务时**不**打印摘要（不污染输出）
- 仅影响 `list` / `stats` / `search` 三个查询类命令；`add` / `update` / `archive` 等写命令不触发
- 详细 BDD：[docs/behaviors/todo-auto-archive-behavior.md](behaviors/todo-auto-archive-behavior.md)

**退出码**：
- 0：成功（包括空仓库/无匹配，输出 `📭 没有任务`）
- 2：非法 status / priority 值

---

### 2.3 `x todo add <名称>` — 添加任务

**用法**：
```bash
x todo add <名称> [选项]
```

**必填参数**：

| 参数 | 说明 |
|------|------|
| `<名称>` | 任务名称（必填）|

**选项**：

| 选项 | 默认值 | 说明 |
|------|--------|------|
| `--priority <优先级>` | `medium` | high / medium / low |
| `--deadline <日期>` | 不写 | YYYY-MM-DD |
| `--tags <标签>` | 不写 | 逗号分隔（如 `驾照,暑假`）|

**示例**：
```bash
# 最简
x todo add "科目一模拟考"

# 完整
x todo add "科目一模拟考" --priority high --deadline 2026-08-31 --tags 驾照,暑假
```

**输出**（成功）：
```
✅ 任务已创建：科目一模拟考（ID: kemu1）
```

**ID 生成规则**：
- 中文：拼音首字母 + 数字后缀（如 `kemu1`）
- 英文：kebab-case（如 `setup-blog`）
- 重复：自动加 `-2` / `-3` / …

**退出码**：
- 0：成功
- 2：任务名为空 / 非法 priority / 非法 deadline 格式
- 3：任务名已存在

---

### 2.4 `x todo update <id>` — 更新任务

**用法**：
```bash
x todo update <id> [选项]
```

**必填参数**：

| 参数 | 说明 |
|------|------|
| `<id>` | 任务 ID（如 `kemu1`）或活动任务名 |

**选项**（**至少要传一个**）：

| 选项 | 说明 |
|------|------|
| `--status <状态>` | 新状态（pending / in_progress / blocked / waiting / archived）|
| `--priority <优先级>` | 新优先级（high / medium / low）|
| `--deadline <日期>` | 新截止日期（YYYY-MM-DD；**传 `""` 显式清除**）|
| `--tags <标签>` | 新标签（逗号分隔；**完全替换而非合并**）|

> ⚠️ **至少要传一个 --xxx 选项**，否则 argparse 报错退出 2

**示例**：
```bash
# 更新状态
x todo update kemu1 --status in_progress

# 同时改 priority 和 deadline
x todo update kemu1 --priority high --deadline 2026-07-01

# 替换 tags（不是合并）
x todo update kemu1 --tags 驾照,考试

# 清除 deadline
x todo update kemu1 --deadline ""
```

**输出**（成功）：
```
✅ 任务已更新：科目一模拟考（ID: kemu1）
```

**字段保留保证**：
- 未知字段（如 `description` / `paused_at` / `pause_reason`）**原样保留**（手写 parser + Task.extra round-trip）
- 改 tags 时是**完全替换**（不是追加/合并）

**退出码**：
- 0：成功
- 2：无 --xxx 选项 / 非法 status / 非法 priority
- 3：任务不存在
- 4：任务已归档（不可 update；要先 restore，未实现）

---

### 2.5 `x todo archive <id>` — 归档任务

**用法**：
```bash
x todo archive <id> [选项]
```

**必填参数**：

| 参数 | 说明 |
|------|------|
| `<id>` | 任务 ID 或任务名 |

**选项**：

| 选项 | 默认值 | 说明 |
|------|--------|------|
| `--reason <原因>` | `done` | 归档原因，**只接受英文枚举**：`done` / `cancelled` / `expired` / `failed` |

**示例**：
```bash
# 归档（默认 done）
x todo archive kemu1

# 取消
x todo archive kemu1 --reason cancelled

# 过期
x todo archive old-task --reason expired

# 失败
x todo archive failed-task --reason failed
```

> ⚠️ **不接受中文 reason**（如 `--reason "已完成"`），是 **--reason "已完成" 的严格子集**

**输出**（成功）：
```
✅ 任务已归档：科目一模拟考（ID: kemu1，reason=done）
```

**归档效果**：
- 文件夹从 `任务/<name>/` 移到 `归档/<YYYYMMDD>-<name>/`（YYYYMMDD = 今天日期）
- frontmatter 加 `status: archived` + `reason: <原因>`
- 总索引 `TODO.md` 自动更新（active 桶 -1，归档桶 +1）

**退出码**：
- 0：成功
- 2：非法 reason
- 3：任务不存在
- 4：任务已归档（重复 archive）
- 5：归档目标文件夹已存在（碰撞）

---

### 2.6 `x todo stats` — 统计信息

**用法**：
```bash
x todo stats
```

**示例**：
```bash
x todo stats
```

**输出**：
```
📊 TODO 统计信息

总任务数：34
- pending：2
- in_progress：2
- blocked：0
- waiting：0
- archived：30

优先级分布：
- high：17
- medium：2
- low：15

即将到期（7 天内）：1
🔥 高优先级任务：3（pending: 1 / in_progress: 2）
```

**说明**：
- `总任务数 = pending + in_progress + blocked + waiting + archived`（**不含** broken 文件）
- `即将到期（7 天内）`：只算 active 任务的 deadline（不含 archived）
- `🔥 高优先级`：只算 active 的 high（pending + in_progress）
- 详细 BDD：`docs/behaviors/todo-stats-behavior.md`

**自动归档（opt-in）**：

当配置文件 `<xcli_data_dir>/config.yaml` 设 `todo.auto_archive: true`，或环境变量 `XCLI_TODO_AUTO_ARCHIVE=1` 时，本命令进入时**先**归档所有 `deadline < today()` 的活动任务（`reason=expired`），再计算统计数字。这意味着：

- stdout **顶部**会先打印一行摘要：`⏰ 自动归档 N 个逾期任务：id1 / id2 / ...`
- 紧接其后才是统计输出（`archived` 计数已包含刚归档的任务）
- 0 个逾期任务时**不**打印摘要
- 详细 BDD：[docs/behaviors/todo-auto-archive-behavior.md](behaviors/todo-auto-archive-behavior.md)

**退出码**：
- 0：成功（无 broken 文件）
- 5：检测到 YAML 解析失败的文件（stderr 输出每条错误，stdout 仍打印统计）

---

### 2.7 `x todo search <keyword>` — 跨字段模糊搜索

**用法**：
```bash
x todo search <关键词> [选项]
```

**选项**：

| 选项 | 说明 |
|------|------|
| `--active-only` | 只搜活动任务（默认搜全部） |
| `--archived-only` | 只搜归档任务（与 `--active-only` 互斥） |
| `--status <状态>` | 按 status 过滤（与搜索结果 AND 关系） |

搜索范围：跨字段模糊匹配 `name` + `note` + `tags`（不区分大小写；逐字符宽松匹配）。

**自动归档（opt-in）**：

当配置文件 `<xcli_data_dir>/config.yaml` 设 `todo.auto_archive: true`，或环境变量 `XCLI_TODO_AUTO_ARCHIVE=1` 时，本命令进入时**先**归档所有 `deadline < today()` 的活动任务（`reason=expired`），再执行搜索。

- stdout **顶部**先打印一行摘要：`⏰ 自动归档 N 个逾期任务：id1 / id2 / ...`
- 紧接其后才是搜索结果表
- **搜索 leak 防护**：auto-archive 触发 search 时，**默认**强制 `include_archived=False`（刚归档的逾期任务**不会**出现在结果表里）。如果用户显式传 `--archived-only`，则保留 `include_archived=True`（用户明确想要归档搜索）
- 0 个逾期任务时**不**打印摘要
- 详细 BDD：[docs/behaviors/todo-auto-archive-behavior.md](behaviors/todo-auto-archive-behavior.md)

**退出码**：
- 0：成功（0 匹配也算 0）
- 2：关键词为空 / `--active-only` 与 `--archived-only` 同时使用 / 非法 `--status` 值

---

## 3. `x skill` — 技能管理（**未实现**）

### 3.1 子命令概览

| 子命令 | 状态 | 说明 |
|--------|------|------|
| `x skill list` | ❌ 未实现 | 列出已安装技能 |
| `x skill install <名称>` | ❌ 未实现 | 安装技能 |
| `x skill update <名称>` | ❌ 未实现 | 更新技能 |
| `x skill remove <名称>` | ❌ 未实现 | 卸载技能 |

> **计划位置**：`<legacy-skills-dir>/`（已存在，是 mavis skills 的存放点；与未来 x-cli skill 集成待定）

---

## 4. `x system` — 系统工具（**未实现**）

### 4.1 子命令概览

| 子命令 | 状态 | 说明 |
|--------|------|------|
| `x system backup` | ❌ 未实现 | 备份 `<legacy-config-dir>/` |
| `x system sync` | ❌ 未实现 | 同步到云端（rclone）|
| `x system health` | ❌ 未实现 | 检查系统健康状态 |
| `x system log` | ❌ 未实现 | 查看日志 |

---

## 5. 退出码速查表

| 退出码 | 含义 | 触发场景 |
|--------|------|---------|
| 0 | 成功 | 所有 action 正常完成 |
| 1 | 通用错误 | 未知子命令 / 占位 action |
| 2 | 参数错误 | 非法 status/priority/reason/deadline / 缺必填参数 / 缺 --xxx |
| 3 | 任务不存在 | list / update / archive 找不到任务 |
| 4 | 任务已归档 | 重复 archive / 对已归档任务 update |
| 5 | 数据完整性 | YAML 解析失败 / 归档目标碰撞 |

---

## 6. 缩写支持（**未实现**）

### 6.1 子命令缩写

**MVP 阶段**：不支持缩写（保持简单）。

**后期扩展**（Phase 4+）：支持子命令缩写
```bash
# 完整命令
x todo list

# 缩写（未来）
x t l
```

### 6.2 自动缩写（**无计划**）

> 不计划实现 — argparse 不原生支持，argcomplete Tab 补全更直接。

---

## 7. Tab 补全（**未实现**）

### 7.1 启用 Tab 补全（计划）

**bash**：
```bash
# 添加到 ~/.bashrc
eval "$(register-python-argcomplete x)"
```

**zsh**：
```bash
# 添加到 ~/.zshrc
eval "$(register-python-argcomplete x)"
```

### 7.2 补全示例（计划）

```bash
x <TAB><TAB>
todo    skill    system

x todo <TAB><TAB>
list    add     update  archive  stats

x todo add --<TAB><TAB>
--priority    --deadline    --tags
```

> **未实现** — 需要 `argcomplete` 依赖；MVP 阶段不引

---

## 8. BDD 行为规格索引

每个 action 都有完整的 Given-When-Then 场景文档：

| 命令 | BDD 文档 | 场景数 |
|------|---------|--------|
| `x todo add` | [todo-add-behavior.md](behaviors/todo-add-behavior.md) | 8 |
| `x todo list` | [todo-list-behavior.md](behaviors/todo-list-behavior.md) | 8 |
| `x todo update` | [todo-update-behavior.md](behaviors/todo-update-behavior.md) | 8 |
| `x todo archive` | [todo-archive-behavior.md](behaviors/todo-archive-behavior.md) | 8 |
| `x todo stats` | [todo-stats-behavior.md](behaviors/todo-stats-behavior.md) | 7 |
| **合计** | — | **39 场景** |

每个 BDD 场景都有对应的 pytest 用例（在 `tests/test_todo_*.py`）。

---

*本文档是活文档，随命令集扩展更新。MVP 实际状态时间：2026-06-21。*
