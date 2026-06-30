# PLAN-v0.5 — TODO 增强 + 数据导出 路线图

> **状态**：🚧 实现中（Phase A ✅ / Phase B ✅ / Phase C ✅ / Phase D ⏳ / Phase E ⏳）
> **来源**：用户桌面 `x-cli功能建议.md`（v1.0，2026-06-30）+ COMMANDS.md ⏳ 区既有承诺
> **作者**：Xavier（决策）+ AI（起草 / 实现）
> **版本**：v0.5.0（接续 v0.4.y）
> **范围**：TODO 子系统增强 + 数据导出（secret 子系统不在本规划内）
> **最后更新**：2026-06-30（Phase C 完成后）

### 阶段状态

| Phase | 内容 | 状态 | Commits |
|---|---|---|---|
| — | 规划（PLAN-v0.5.md）| ✅ | `4473013` |
| A | P0 时间精度（--time / --end-time / --duration）| ✅ | `ef9ce68` `f2c6732` `88f5dfd` |
| B | P1 子任务（--parent / 2 层 / 永远级联）| ✅ | `7b4bf30` `e7c54d9` `0075401` |
| C | P1 提醒只读 + list --reminding + stats 统计 | ✅ | `34b85a9` `13ef32c` `2b9a032` |
| D | P2 重复 / 批量 / 排序 / urgent / 回收站 | ⏳ | — |
| E | P3 模板 / 依赖 / 导出 | ⏳ | — |
| — | 附加修复（date-fragile test + pytest tmpdir workaround）| ✅ | `3a76f17` |

**累计新增**：43 用例 + 1 修复 + 1 workaround，全部 PASS。全量 619/620。

---

## 0. TL;DR

本版本目标是把 TODO 从「日期粒度的扁平清单」升级为「时间点/时间段感知的层级化任务系统」，并补齐批量、提醒、模板、依赖、导出等高频场景。

| 项 | 值 |
|---|---|
| 涉及插件 | `plugins/todo.py`（主战场）+ `core/models.py` + `core/storage.py` + `core/parser.py` + `core/formatting.py`（颜色检测）|
| 新增子命令 | 6（`todo edit` / `todo tag` / `todo remove` / `todo repeat-fire` / `todo export` / `todo template` + `todo reminder list/clear`）|
| 新增 flag | ≥ 11（`--time` / `--end-time` / `--duration` / `--parent` / `--repeat` / `--remind` / `--sort` / `--tag` 多值 / `--depends` / `--no-color` / `--all` / `--reminding` / `--tree`）|
| 数据模型扩展 | `time` / `end_time` / `duration_min` / `parent` / `repeat` / `remind` / `depends` / `priority` 新枚举值 `urgent` |
| BDD 规格 | 10 份新 spec |
| 测试增量 | 估计 +90 用例（Phase C 由 15 减到 10，因 v0.5 不实装 daemon）|
| 向后兼容 | ✅ 全部新字段可选，旧任务文件夹不需迁移 |
| 关键非目标 | v0.5 提醒**不触发通知**（等 v0.6+ exe 打包后）/ 子任务限 **2 层** / 父任务操作**永远级联** / 重复触发**显式 `repeat-fire`** |

**预计落地顺序**（后述）：P0 时间精度 → P1 子任务 / 提醒只读 / 标签筛选 → P2 重复 / 批量 / 排序 / `urgent` → P3 模板 / 依赖 / 导出。

---

## 1. 目标 & 非目标

### 1.1 目标

1. **时间维度精确到分钟** — 考试 / 会议 / 课程有时间点，必须能存能显能筛
2. **任务可分解（2 层）** — 复杂流程（退宿 / 装修 / 旅行）能用子任务 + 孙任务管理（限 2 层避免复杂度爆炸）
3. **减少遗忘（v0.5 部分）** — 提醒字段可写可显可清，**v0.5 不触发通知**（等 exe 打包后 v0.6+ 实装）
4. **重复任务（显式触发）** — 日常 / 周常 / 自定义 cron 周期任务，用户手动 `repeat-fire` 创建下一次实例（避免 archive 时误触）
5. **批量操作** — 一次处理多个任务（批量 done / archive / update / remove）
6. **数据可移植** — JSON / CSV / Markdown 三种格式导出，便于备份和外部工具消费

### 1.2 非目标（明确不做）

- ❌ **不做交互式 TUI**（rich / textual）— 个人 CLI，表格 + emoji 已够
- ❌ **不做日历集成**（CalDAV / Google Calendar）— v0.6+ 提醒走系统通知
- ❌ **不做多人协作** — 单用户工具
- ❌ **不做邮件 / 微信通知** — v0.6+ 仅系统通知（`msg` / `osascript` / `notify-send`）
- ❌ **不引第三方依赖**（croniter / plyer / send2trash / dateparser）— stdlib-only 原则不变
- ❌ **不做子命令缩写** — `x t a` 不支持
- ❌ **v0.5 不做后台 daemon** — 等 exe 打包后再实装提醒触发

---

## 2. 优先级与功能清单

> 优先级 = 用户痛点 × 实现成本。P0 必须做，P1 应该做，P2 做了更好，P3 看心情。

### 🔥 P0 — 时间精度（考试/会议刚需）

#### 2.1.1 `--time HH:MM` 精确到分钟

```bash
x todo add "科目一模拟考" --deadline 2026-08-31 --time 08:20
x todo update kjj-moni --time 09:00
```

**存储**：`TODO.md` frontmatter 新字段 `time: "08:20"`（24h 制，字符串）
**兼容**：旧任务无 `time` 字段视为「全天」

#### 2.1.2 `--end-time HH:MM` 时间段

```bash
x todo add "考试" --deadline 2026-07-03 --time 08:20 --end-time 09:50
```

**存储**：`end_time: "09:50"` 字段
**互斥**：与 `--duration` 互斥（同时给 → 退出码 2）

#### 2.1.3 `--duration <时间长度>` 持续时间

```bash
x todo add "复习" --deadline 2026-07-02 --time 19:00 --duration 1.5h
x todo add "会议" --time 14:00 --duration 90m
```

**支持格式**：`Nh` / `Nm` / `N`（默认分钟）/ `N.Nh`（小数小时）
**存储**：计算后存 `duration_min: 90`（整数分钟）
**互斥**：与 `--end-time` 互斥

#### 2.1.4 列表展示时间点

```
ID              Name              Status    Priority  Deadline       Time
──────────────  ────────────────  ────────  ────────  ─────────────  ────────
t-fd316ca8      科目一模拟考      ⏳        🔥 high   2026-08-31     08:20
```

新增 `Time` 列，无 `time` 字段显示 `-`

---

### ⚡ P1 — 子任务 / 提醒 / 标签筛选

#### 2.2.1 `--parent <id>` 子任务（**2 层**）

```bash
x todo add "退宿离校" --deadline 2026-07-13
x todo add "清扫宿舍" --parent t-fd316ca8        # 子任务
x todo add "擦窗户" --parent t-abc123             # 孙任务（2 层）
```

**存储**（`parent` 字段而非嵌套 `children`）：
```yaml
id: t-abc123
name: 清扫宿舍
parent: t-fd316ca8
```

**为什么选 parent 字段**：单文件独立性，每任务可单独 archive / edit / move；树形展示在 list 时计算，不污染存储
**层级**：允许 **2 层**（parent → child → grandchild），模板场景需要；不限制 3+ 层避免复杂度爆炸
**展示**（`x todo list --tree` 或自动启用当存在 parent 时）：
```
t-fd316ca8      退宿离校          ⏳  🔥 high   2026-07-13
  └ t-abc123    清扫宿舍          ⏳  🔥 high   -
    └ t-xyz789  擦窗户            ⏳  🔥 high   -
  └ t-def456    清点物品          ⏳  🔥 high   -
```

**archive / remove 父任务 → 永远级联** ✅
- archive 父任务 → 所有后代（子 + 孙）一起 archive，reason 跟父任务一致
- remove 父任务 → 所有后代一起进回收站
- 破坏性操作（remove 级联）弹 y/N 确认，输入 `n` 取消整个操作
- 子任务独立 archive / remove 不影响父和其他后代

#### 2.2.2 `--remind <提前时间>` 智能提醒（**v0.5 默认关闭**）

```bash
x todo add "考试" --deadline 2026-07-03 --time 08:20 --remind 1d
x todo add "会议" --time 14:00 --remind 30m
x todo add "重要会议" --deadline 2026-07-05 --remind 1d,2h,30m
```

**支持格式**：`Nd` / `Nh` / `Nm`（同 `--duration`），逗号分隔多值
**存储**：`remind: ["1d", "2h", "30m"]`（数组）

**v0.5 默认行为：提醒**关闭** ❌**
- 原因：x-cli 当前是 `python -m x` / `x.bat` wrapper 启动，**没有独立 exe 进程**，daemon 无宿主；Windows 上没有合适的常驻方式
- 字段可写、列表可显、统计可算，但**不会触发任何系统通知**
- 等 v0.6+ 打包 exe 后再实装 `x todo reminder daemon` + 跨平台通知

**v0.5 范围内仍提供的能力（不触发通知）**：
- `x todo reminder list` — 查看带 remind 字段的任务（只读）
- `x todo reminder clear <id...>` — 清空任务的 remind 字段
- `x todo list --reminding` — 筛选带 remind 的任务
- `x todo stats` 增加「⏰ 有提醒任务数」统计

**未来 v0.6+ 启用路径**（占位）：
- Windows: 独立 `x.exe --reminder-daemon` + 注册为 Windows Service / Task Scheduler
- macOS: launchd plist
- Linux: systemd user unit
- 通知：stdlib `subprocess` 调系统命令（`msg` / `osascript` / `notify-send`），不引 plyer

#### 2.2.3 `--tag` 多值筛选（增强）

当前 `--tag` 已支持，本次增强为：
- 多次 `--tag` 走 AND 关系
- 支持 `key:value` 精确匹配（`--tag "地点:2507右"`）

```bash
x todo list --tag "考试" --tag "7月"            # 同时含两个标签
x todo list --tag "地点:2507右"                  # key:value 精确
```

---

### 📝 P2 — 重复 / 批量 / 排序 / 紧急优先级

#### 2.3.1 `--repeat <规则>` 重复任务（**显式 `repeat-fire` 触发**）

```bash
x todo add "周会" --repeat weekly --time 14:00
x todo add "吃药" --repeat daily --time 08:00
x todo add "打卡" --repeat weekdays --time 09:00
x todo add "备份" --repeat "0 8 * * 1-5"

# 手动触发下一次实例
x todo repeat-fire t-zhihui-001
```

**支持语法**：
| 写法 | 含义 |
|---|---|
| `daily` | 每天 |
| `weekly` | 每周（周一，存首次触发日期）|
| `weekdays` | 周一到周五 |
| `monthly` | 每月（同日）|
| 标准 cron | 5 字段（分 时 日 月 周）|

**存储**：`repeat: { kind: "weekly" }` 或 `repeat: { cron: "0 8 * * 1-5" }`
**触发机制**：**显式 `x todo repeat-fire <id>`**，archive --reason done 时不自动创建（避免误触）
**实例命名**：在原 ID 末尾加 `-<seq>` 后缀（001 / 002 / ...），新实例继承 repeat 规则
- `t-zhihui` → done 后 → `t-zhihui-001` → done 后 → `t-zhihui-002`
- seq 自动累加（扫现有实例取 max + 1）
- 原任务保留，作为「模板/锚点」，不删除
**不做**：不引 `croniter`，手写 next-fire 计算（硬编码月/日规则表 + `datetime` stdlib）

#### 2.3.2 批量操作

```bash
# 批量 done（已存在，扩展为接受任意数量 id）
x todo done t-aaa t-bbb t-ccc

# 批量 archive
x todo archive t-aaa t-bbb --reason cancelled

# 批量 update
x todo update --filter "考试" --deadline 2026-07-03

# 批量 remove（新增子命令，**走回收站**）
x todo remove t-aaa t-bbb
```

`--filter <keyword>` 是模糊匹配（name + tags + note）

**`remove` 走系统回收站（可恢复）** ✅ 已确认
- Windows: `ctypes` 调 `SHFileOperation` (FO_DELETE) — stdlib-only
- macOS: `subprocess` 调 `osascript` 移动到 Trash
- Linux: `subprocess` 调 `gio trash` / `trash-cli` (XDG Trash)
- 区别于 `archive`：archive 是软删除（标记 + 移 archive/ 子目录，可 list --archived 找回）；remove 是物理删除（但走回收站，可手动还原）
- `--force` flag 跳过回收站直接物理删除（危险操作，红色警告）

#### 2.3.3 列表排序

```bash
x todo list --sort priority      # 默认
x todo list --sort deadline
x todo list --sort created       # 旧默认行为
x todo list --sort time          # 按 time 字段
```

#### 2.3.4 `urgent` 优先级（**排序 + ANSI red 高亮**）

```bash
x todo add "明天考试" --priority urgent
```

**枚举扩展**：`low` / `medium` / `high` / **`urgent`**
**存储**：`priority: "urgent"`
**图标**：🔥🔥（双火焰）+ ANSI red 颜色（`\x1b[31m`）
**与 high 的区别**：list 排序时 `urgent` > `high` > `medium` > `low`，**且 urgent 任务在终端显示为红色**
**颜色兼容性**：自动检测终端能力（详见 §6.5）
- 支持 ANSI 的终端：Linux / macOS 终端、VS Code 集成终端、Windows Terminal
- 不支持（Windows cmd）：回退为无颜色（仅 🔥🔥 图标区分）
- `--no-color` flag 全局禁用

---

### 💡 P3 — 模板 / 依赖 / 导出

#### 2.4.1 任务模板

```bash
# 创建
x todo template create "退宿流程" \
  --steps "清扫宿舍,清点物品,宿管核验,交表"

# 使用
x todo add "退宿" --template "退宿流程" --deadline 2026-07-13
```

**存储**：模板文件存 `<xcli_data_dir>/templates/<name>.yaml`
**使用效果**：展开为父任务 + N 个子任务（自动 `--parent`）

#### 2.4.2 任务依赖 `--depends`

```bash
x todo add "复习" --deadline 2026-07-02
x todo add "考试" --deadline 2026-07-03 --depends t-review
```

**存储**：`depends: [t-review]`（数组）
**列表增强**：有未完成依赖的任务显示「🔒 等待 t-review」
**不做**：不做循环依赖检测（用户自己保证）

#### 2.4.3 数据导出

```bash
x todo export --format json --output tasks.json
x todo export --format csv --output tasks.csv
x todo export --format md --output tasks.md
```

**格式**：
- JSON: 完整 frontmatter + body
- CSV: 扁平表（id, name, status, priority, deadline, time, tags, parent, archived_at）
- MD: 表格（人类可读）

---

## 3. 数据模型扩展

### 3.1 TODO.md frontmatter 新字段一览

| 字段 | 类型 | 默认 | 说明 | 阶段 | 状态 |
|---|---|---|---|---|---|
| `time` | str `HH:MM` | — | 开始时间 | A | ✅ |
| `end_time` | str `HH:MM` | — | 结束时间（与 `duration_min` 互斥）| A | ✅ |
| `duration_min` | int | — | 持续分钟数 | A | ✅ |
| `parent` | str | — | 父任务 ID（2 层上限）| B | ✅ |
| `depends` | list[str] | `[]` | 依赖任务 ID 列表 | E | ⏳ |
| `repeat` | dict | — | 重复规则（见 §2.3.1）| D | ⏳ |
| `remind` | list[str] | `[]` | 提前时间列表 | C | ⏳（字段已实装，通知功能推迟 v0.6+）|

### 3.2 优先级枚举扩展

```python
class Priority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"   # 新增（Phase D 落地）
```

### 3.3 向后兼容

- 所有新字段**可选**，parser 缺失时给 None / `[]`
- 旧任务文件夹不动，不需 migration 命令
- list 输出新列时，旧任务对应列显示 `-`

---

## 4. CLI 表面新增

### 4.1 新 flag（`x todo add` / `x todo update` 通用）

| Flag | 类型 | 默认 | 备注 |
|---|---|---|---|
| `--time` | `HH:MM` | — | P0 |
| `--end-time` | `HH:MM` | — | P0，与 `--duration` 互斥 |
| `--duration` | `1.5h` / `90m` / `90` | — | P0，与 `--end-time` 互斥 |
| `--parent` | task id | — | P1 |
| `--depends` | task id（可多次）| — | P3 |
| `--repeat` | `daily`/`weekly`/`weekdays`/`monthly`/cron | — | P2 |
| `--remind` | `1d,2h,30m` | — | P1 |
| `--template` | 模板名 | — | P3（仅 add）|

### 4.2 新子命令

| 命令 | 用途 |
|---|---|
| `x todo edit <id>` | 用 `$EDITOR` 打开 TODO.md（COMMANDS.md ⏳ P1 旧承诺）|
| `x todo tag <id> <标签...>` | 单独管理 tags（不重写整个任务）|
| `x todo remove <id...>` | 物理删除 → **走系统回收站**（`--force` 跳过回收站 / 级联子任务时 y/N 确认）|
| `x todo repeat-fire <id>` | **显式触发**重复任务的下一次实例（v0.5 不自动）|
| `x todo export` | 导出 JSON/CSV/MD |
| `x todo template create/list/remove` | 模板管理 |
| `x todo reminder list/clear` | v0.5 只读 / 清除（**不触发通知**）|

### 4.3 全局 flag

| Flag | 用途 |
|---|---|
| `--no-color` | 全局禁用 ANSI 颜色（默认自动检测）|
| `--all` | `update --filter` / `remove` 扩到 archived 范围（默认 active only）|

### 4.4 list 新 flag

| Flag | 默认 |
|---|---|
| `--sort priority` | ✅（新默认）|
| `--sort deadline` / `--sort created` / `--sort time` | 互斥 |
| `--tree` | 树形展示子任务（自动启用 if 任一任务有 parent）|
| `--tag` 可多次 | AND 关系 |
| `--reminding` | 筛选带 remind 字段的任务 |

---

## 5. 实现阶段（按 BDD + TDD）

### Phase A — P0 时间精度（1 个 spec，17 用例） ✅ 完成

1. **BDD**: `docs/behaviors/todo-time-precision-behavior.md` ✅
2. **TDD**: `tests/test_todo_time_precision.py` ✅（17/17 Red）
3. **实现**: `core/models.py` + `core/slug.py` + `core/storage.py` + `plugins/todo.py` ✅
4. **验收**: 17/17 Green ✅
5. **提交**: `ef9ce68` (BDD) / `f2c6732` (Tests) / `88f5dfd` (Impl)

### Phase B — P1 子任务（1 个 spec，13 用例） ✅ 完成

1. **BDD**: `docs/behaviors/todo-parent-behavior.md` ✅（合并 tree display 进 parent spec）
2. **TDD**: `tests/test_todo_parent.py` ✅（13/13 Red）
3. **实现**: `core/models.py` 加 parent 字段 + `core/storage.py` 加 `find_descendants()` + `plugins/todo.py` ✅
4. **验收**: 13/13 Green ✅
5. **提交**: `7b4bf30` (BDD) / `e7c54d9` (Tests) / `0075401` (Impl)
6. **注**: 原计划的 `test_todo_tree.py` 合并进 `test_todo_parent.py`（parent 与 tree 是同一概念）

### Phase C — P1 提醒只读（13 用例） ✅ 完成

1. **BDD**: `docs/behaviors/todo-remind-behavior.md` ✅（12 场景）
2. **TDD**: `tests/test_todo_remind.py` ✅（13/13 Red）
3. **实现**: `core/models.py` + `core/slug.py` + `core/storage.py` + `plugins/todo.py` ✅
4. **验收**: 13/13 Green ✅
5. **提交**: `34b85a9` (BDD) / `13ef32c` (Tests) / `2b9a032` (Impl)
6. **超出预期**: BDD 写的是 12 场景，测试多加了 1 个（`--remind ""` 空字符串省略字段），覆盖 add + update 两端

**v0.5 不做**：daemon 进程 / 系统调度器注册 / 通知触发（推到 v0.6+ 打包 exe 后）

**实现期发现**：
- `parse_duration` 原只支持 `Nh/Nm`，remind 需要 `Nd`，扩展 regex + 单位换算
- `parse_remind` 复用 `parse_duration` 但报错信息需明确说「remind」而非「duration」（避免误导用户）
- `TODO_ACTIONS` tuple 加 `reminder` 后才能被子命令 dispatch
- 每次 Phase 加新字段（如 Phase B `parent`、Phase C `remind`）都需同步更新 `tests/test_todo_stats.py` 里手搓 Namespace 的 `test_update_legacy_archived_task_is_blocked`

### Phase D — P2 重复 + 批量 + 排序 + urgent + 回收站（4 个 spec，预计 +30 用例）

1. **BDD**:
   - `todo-repeat-behavior.md`（repeat 字段 + `repeat-fire` 子命令 + 实例命名 -<seq>）
   - `todo-batch-behavior.md`（done / archive / update / remove 多 id + --filter）
   - `todo-sort-behavior.md`（4 种 sort + tree + reminding 筛选）
   - `todo-urgent-behavior.md`（urgent 枚举 + ANSI red 高亮 + 终端检测）
2. **TDD**: 对应 4 个 test 文件
3. **实现**:
   - repeat 解析（手写 cron）+ `x todo repeat-fire <id>` 子命令
   - batch handler（多 id 接受 + --filter 模糊匹配 + --all flag 扩到 archived）
   - sort logic（priority / deadline / created / time）
   - `urgent` 枚举 + ANSI red + 终端颜色检测（`core/formatting.py:supports_color()`）
   - **回收站**支持：`core/recycle.py`（stdlib-only，Win ctypes + macOS subprocess + Linux gio trash）

### Phase E — P3 模板 + 依赖 + 导出（3 个 spec，预计 +20 用例）

1. **BDD**: `todo-template-behavior.md` + `todo-depends-behavior.md` + `todo-export-behavior.md`
2. **TDD**: 对应测试文件
3. **实现**: 模板存储 + 依赖展示 + JSON/CSV/MD 序列化器

**总计**：10 个 BDD spec + 10 个 test 文件 + ~90 用例 + 全量 ~425 用例（Phase C 由 15 减到 10，因 v0.5 不实装 daemon）

---

## 6. 关键设计决策

### 6.1 子任务：用 `parent` 字段而非嵌套 `children`

**理由**：
- 单文件独立性（每任务可单独 archive / edit / move）
- 删除父任务不级联（避免误删）
- 与文件系统布局对齐（每个 task = 一个文件夹）
- 树形展示在 list 时计算，不污染存储

**代价**：查询子任务需扫所有任务 + 过滤 parent。性能 OK（< 1000 任务场景下 < 10ms）。

### 6.2 提醒机制：v0.5 关闭，v0.6+ 再选 daemon / scheduler

**v0.5 决策**：提醒**默认关闭**，字段可写但不触发任何通知
- 原因：x-cli 当前是 `python -m x` / `x.bat` wrapper 启动，没有独立 exe 进程，daemon 无宿主
- v0.5 提供只读 / 清除 / 统计能力（`reminder list / clear / list --reminding`）

**v0.6+ 候选方案**（届时再定）：
- 方案 A：独立 daemon（`x todo reminder daemon`），每分钟扫一遍
  - 优点：跨平台统一，用户体验一致
  - 缺点：需后台进程，Windows 上需注册 service
- 方案 B：注册到系统调度器（Task Scheduler / launchd / cron）
  - 优点：原生集成，关机不丢
  - 缺点：每次提醒触发都新建一个任务

**依赖前提**：v0.6+ 必须先完成 exe 打包（PyInstaller --onefile），否则方案 A 没法落地

### 6.3 重复任务：手写 cron 解析

**理由**：
- `croniter` 是 PyPI 包（违反 stdlib-only 原则）
- 用户重复规则简单（daily/weekly/weekdays/monthly/标准 5 字段 cron），手写 ~80 行可覆盖
- 不支持秒级 / 年字段（超出个人需求）

**实现**：硬编码月/日/周规则表 + `datetime.timedelta` 算 next fire

### 6.4 数据导出格式

| 格式 | 用途 |
|---|---|
| JSON | 备份 + 跨工具消费（最完整）|
| CSV | Excel / Numbers 打开（最常用） |
| Markdown | 人类阅读 + 贴到笔记（最易读）|

**CSV 多值编码**：tags / remind / depends 等多值字段用 `;` 分号分隔（Excel 友好）
**三种格式**都从同一 `to_dict()` 出发，避免重复实现

### 6.5 终端颜色检测（urgent 高亮用）

**检测策略**：
1. `sys.stdout.isatty()` 为 False → 无颜色（重定向 / pipe 时）
2. `--no-color` 显式禁用
3. 环境变量 `NO_COLOR` 存在（[no-color.org](https://no-color.org/) 标准）→ 无颜色
4. Windows 上额外检查 `WT_SESSION`（Windows Terminal）或 `TERM` 含 `xterm`/`ansi` → 启用 VT100
5. Windows cmd（无 WT_SESSION、TERM=dumb）→ 启用 VT100 mode（`ctypes` 调 `SetConsoleMode` + `ENABLE_VIRTUAL_TERMINAL_PROCESSING`），失败回退无颜色

**实现位置**：`core/formatting.py:supports_color() -> bool`（已有 CJK 对齐函数，复用同文件）

### 6.6 父任务 archive / remove 永远级联

**用户决策（Q13）**：无 `--cascade` flag，永远级联子 + 孙
- archive 父 → 后代全部 archive，reason 沿用父的 reason
- remove 父 → 后代全部走回收站
- remove 级联时弹 **y/N 确认**（输入 `n` 取消整个操作，避免误删）
- 单元测试：cascade 覆盖（子 + 孙 + 同名任务不会混淆）

---

## 7. 待决策 / Open Questions

### 已答

- [x] **Q1（原）**: 提醒机制 → **v0.5 默认关闭**，v0.6+ 打包 exe 后再选 daemon vs scheduler
- [x] **Q2**: 重复任务历史 → **每次复制新实例 + `-<seq>` 后缀**
- [x] **Q3**: `--remind` 格式 → **v0.5 仅支持相对时间** `Nd/Nh/Nm`（绝对时间等 v0.6+ 启用通知后再加）
- [x] **Q4**: 模板路径 → **`<xcli_data_dir>/templates/`**（统一）
- [x] **Q5（原）**: `x todo remove` → **走系统回收站**（`--force` 跳过）
- [x] **Q6**: CSV 多值字段 → **`;` 分号分隔**（Excel 友好）
- [x] **Q7**: 子任务层级 → **允许 2 层**（parent → child → grandchild）
- [x] **Q8**: `update --filter` 范围 → **默认 active only，加 `--all` flag 显式启用**
- [x] **Q9**: `--sort time` 无 time 字段任务 → **排末尾**（按 deadline fallback）
- [x] **Q10**: `urgent` 行为 → **排序 + ANSI red 高亮**（自动检测终端能力，见 §6.5）
- [x] **Q11**: repeat 触发时机 → **显式 `x todo repeat-fire <id>`**，archive 时不自动
- [x] **Q13**: 父任务 archive / remove → **永远级联**（remove 时 y/N 确认）

### 已答 + 文档化（Phase B 期间补答）

- [x] **Q14（新）**: `x todo done`（即 archive --reason done）批量时 → **不再逐个 y/N 确认级联**（用户显式敲命令 = 已确认；父任务级联只在 archive 单个时走，批量整体一次操作）。注：Phase B 实现的是 archive 单个父任务级联，批量级联语义待 Phase D 实装时细化。
- [x] **Q15（新）**: 模板步骤命名 → **允许重复**（slug 自带序号去重，存为子任务时按 `-001 / -002` 追加）

### 已决 + 文档化

- [x] **Q16（隐含）**: stdlib-only 原则下怎么走回收站？
  - Windows: `ctypes` 调 `SHFileOperation(FO_DELETE)`
  - macOS: `subprocess` 调 `mv` 到 `~/.Trash/<timestamp>/`
  - Linux: `subprocess` 调 `gio trash <path>`（`gio` 是 GLib 自带，主流发行版都有）

### 仍开放（影响小，可推进时再决定）

无新增（Phase A + B 没有产生新 Q；Q3 已由 v0.5 不触发通知决定）

### 实现期发现（Phase B 验证后补）

- 父任务 archive 级联时，cycle 检查（self-as-descendant）会在 depth 检查之前先触发；用户看到「子任务最多 2 层」而非「cycle detected」。行为正确，UX 文案 minor。Phase D 再统一优化。
- 列表 `--tree` flag 未提供 `--no-tree`（无 parent 时列表正常不加 indent，隐式 tree 关闭）。已确认符合 BDD 规格。

---

## 8. 与 COMMANDS.md ⏳ 的整合

本规划完成后，COMMANDS.md ⏳ 区应更新为：

```markdown
## ⏳ 我想要的（按优先级排序）

### P0 — 时间精度
- [ ] `x todo add/update --time / --end-time / --duration`（v0.5.0）

### P1 — 立即做
- [ ] `x todo add --parent` 子任务（2 层 + 永远级联）（v0.5.0）
- [ ] `x todo add --remind` 智能提醒（v0.5.0，**仅存储 / 显示 / 清除，不触发通知**）
- [ ] `x todo reminder list / clear` 子命令（v0.5.0）
- [ ] `x todo list --tag` 多值 / `key:value`（v0.5.0）
- [ ] `x todo list --reminding` 筛选（v0.5.0）
- [ ] `x todo edit <id>`（COMMANDS.md P1 旧承诺）
- [ ] `x todo tag <id> <标签...>`（COMMANDS.md P1 旧承诺）
- [ ] `x --config --force`（COMMANDS.md P1 旧承诺）
- [ ] 日志轮转（COMMANDS.md P1 旧承诺）

### P2 — 常用增强
- [ ] `x todo add --repeat` 重复任务（v0.5.0）
- [ ] `x todo repeat-fire <id>` 显式触发下一次实例（v0.5.0）
- [ ] `x todo done / archive / update / remove` 批量 id + `--filter`（v0.5.0）
- [ ] `x todo remove <id...>` 走回收站（v0.5.0，`--force` 跳过）
- [ ] `x todo list --sort` 排序 + `--tree` 树形展示（v0.5.0）
- [ ] `x todo add --priority urgent` + ANSI red 高亮（v0.5.0）
- [ ] `--no-color` 全局 flag（v0.5.0）
- [ ] `x --log-level <level>` 子命令覆盖（COMMANDS.md P2 旧承诺）
- [ ] Config validation / 热重载 / `--help` fix / `secret update --category`（COMMANDS.md P2 旧承诺）

### P3 — 远期
- [ ] `x todo template create/list/remove`（v0.5.0）
- [ ] `x todo add --depends`（v0.5.0）
- [ ] `x todo export`（v0.5.0）
- [ ] `x skill / x agent / x system`（COMMANDS.md P3 旧承诺，**注**：`x web` 已实装）
```

---

## 9. 时间线（粗估）

| 周 | 阶段 | 交付 |
|---|---|---|
| W1 | Phase A（P0 时间精度）| +15 用例，1 spec |
| W2 | Phase B（P1 子任务 2 层 + 级联）| +25 用例，2 spec |
| W3 | Phase C（P1 提醒只读 + 列表筛选 + 统计）| +10 用例，1 spec（**不做 daemon**）|
| W4 | Phase D（P2 重复 / 批量 / 排序 / urgent / 回收站）| +30 用例，4 spec |
| W5 | Phase E（P3 模板 / 依赖 / 导出）| +20 用例，3 spec |
| W6 | 收尾 + 文档同步 + v0.5.0 release | CHANGELOG + README 更新 |

**v0.6+ 待办**（不在本规划范围）：
- PyInstaller 打包 `x.exe`（必需前置）
- 提醒 daemon 实装（独立进程 + 系统调度器）
- 跨平台系统通知（msg / osascript / notify-send）

**前置条件**：每阶段交付前更新本 doc 的「状态」字段

---

## 10. 参考

- 用户建议原件：`C:\Users\Chatxavier\Desktop\x-cli功能建议.md`（v1.0）
- 项目规约：`AGENTS.md` §5 BDD+TDD 流程
- 命令清单：`COMMANDS.md`
- BDD 规格目录：`docs/behaviors/`
- 架构文档：`docs/architecture.md`

---

*文档创建时间：2026-06-30*
*维护者：AI 起草 + 用户 review*