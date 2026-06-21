# x --config / x --log-level 行为规格

> **目标读者**: 接续开发的 AI agent
> **范围**: 全局 `x --config <path>` 和 `x --log-level <level>` 选项，配置 + 日志基础设施
> **对应测试**: `tests/test_config.py` + `tests/test_logging.py`（单元）+ `tests/test_e2e_x.py`（E2E）
> **状态**: 🚧 P1 规划中（2026-06-21）

---

## 为什么需要这个

x-cli 现在每次启动都从 `core/paths.py` 读硬编码的默认路径。但用户会想：
- 改 TODO 库位置（不想用 `%LOCALAPPDATA%\x-cli\todo\`）
- 控制日志级别（debug 时看更多，普通用时安静）
- 设置代理（如果某些 API 在墙后）
- 未来扩展：自定义 LLM 端点 / 时间格式 / etc.

`x --config` 提供 YAML 配置入口，`x --log-level` 控制日志。先做最小可用版本，复杂配置（嵌套 schema、validation）后做。

---

## 路径与不变量

- **默认配置文件**：`xcli_data_dir()/config.yaml`（独立于 xavier 系统的 `~/.xavier/config/`）
  - Windows: `%LOCALAPPDATA%\x-cli\config.yaml`
  - Unix: `~/.local/share/x-cli/config.yaml`
- **环境变量**：`XCLI_CONFIG` 覆盖（指向文件路径，不是目录）
- **配置文件不存在**：第一次启动不报错（用全部默认）；显式 `--config /path/that/doesnt/exist` → 报错退出
- **XDG 兼容**：未来可加 `$XCLI_CONFIG_DIR`（暂不实现）

---

## 场景 1：默认配置（无文件）

**Given**:
- `%LOCALAPPDATA%\x-cli\config.yaml` 不存在

**When**:
- 运行 `x --version`（或任何 x 命令）

**Then**:
- 不报错
- 用全部硬编码默认值：
  ```yaml
  # Effective config (default):
  todo_dir: <xcli_todo_dir()>
  secrets_path: <xcli_secrets_path()>
  log_level: WARNING
  log_path: <xcli_data_dir()>/x.log
  ```
- 日志不写文件（`log_level: WARNING` 时不主动写）

---

## 场景 2：首次写默认配置文件

**Given**:
- 配置文件不存在

**When**:
- 运行 `x --config init`（**新子命令**）

**Then**:
- 退出码 0
- 在 `xcli_data_dir()` 写 `config.yaml`，内容是全部默认值的注释版
- stdout 含 `✅ 配置已写入：<full_path>`
- 不覆盖已存在的文件（`--force` 覆盖）

> **设计选择**：`x --config init` 是新增的子命令，用来生成默认配置。也可以用 `x --config <path>` + 显式提供路径，区别是 init 用平台默认路径，--config 是用户指定。

---

## 场景 3：指定配置文件加载

**Given**:
- `D:\test-config.yaml` 存在，内容：
  ```yaml
  todo_dir: D:\my-projects\tasks
  log_level: DEBUG
  ```

**When**:
- 运行 `XCLI_CONFIG=D:\test-config.yaml x todo list`

**Then**:
- 实际读 `D:\my-projects\tasks\`（**不**读默认 `xcli_todo_dir()`）
- 日志输出到 stderr（log_level=DEBUG → 显示 DEBUG/INFO/WARNING/ERROR 全部）

> **优先级**（高到低）：
> 1. `XCLI_CONFIG` 环境变量（最高）
> 2. `--config <path>` CLI 参数
> 3. `xcli_data_dir()/config.yaml`（默认）
> 4. 硬编码默认（兜底）

---

## 场景 4：--config <path> 覆盖

**Given**:
- 默认配置文件不存在
- `D:\alt-config.yaml` 存在

**When**:
- 运行 `x --config D:\alt-config.yaml todo list`

**Then**:
- 读 `D:\alt-config.yaml`
- 等同于 `XCLI_CONFIG=D:\alt-config.yaml x todo list`

---

## 场景 5：--config 路径不存在 → 报错

**Given**:
- `--config /nonexistent/path/config.yaml`

**When**:
- 运行 `x --config /nonexistent/path/config.yaml todo list`

**Then**:
- 退出码非 0（5：数据完整性错 或 2：参数错）
- stderr 含 `❌ 配置文件不存在：/nonexistent/path/config.yaml`
- **不**回退到默认（用户明确指定了路径，找不到就该报错）

---

## 场景 6：YAML 解析失败

**Given**:
- 配置文件存在但内容损坏（不是 valid YAML）

**When**:
- 运行 `x --config <bad-yaml> todo list`

**Then**:
- 退出码 5
- stderr 含 `❌ 配置文件解析失败：<error>`
- **不**回退到默认（fail fast）

---

## 场景 7：log_level 取值

**Given**:
- `x --log-level DEBUG todo list`

**When**:
- 运行该命令

**Then**:
- 日志输出包含 DEBUG/INFO/WARNING/ERROR 全部
- stderr 含 `[DEBUG]` 前缀（如果用了 stdlib `logging`）
- 不影响 exit code（除非命令本身错）

> **合法值**（按 Python stdlib `logging` 约定）：
> - `DEBUG` (10)
> - `INFO` (20)
> - `WARNING` (30) — 默认
> - `ERROR` (40)
> - `CRITICAL` (50)
> 大小写不敏感（接受 `debug` / `Debug` / `DEBUG`）

---

## 场景 8：log_path 默认（写文件）

**Given**:
- 默认配置：`log_level: WARNING`, `log_path: <xcli_data_dir>/x.log`

**When**:
- 任何 x 命令触发 WARNING/ERROR 日志

**Then**:
- 写一行到 `<xcli_data_dir>/x.log`（带时间戳）
- 同时输出到 stderr（双写，行为可观察）

---

## 场景 9：log_path 设为 null（不写文件）

**Given**:
- 配置：
  ```yaml
  log_path: null  # 或 log_path: ""
  ```

**When**:
- 任何 x 命令触发 WARNING

**Then**:
- stderr 输出 WARNING
- **不**创建 / 写入日志文件

---

## 场景 10：v0.4.x 兼容（不破坏现有行为）

**Given**:
- 用户升级到带 `--config` / `--log-level` 的版本
- 旧用法（`x todo list` 不带任何 flag）继续工作

**When**:
- 运行 `x todo list`（无任何 flag）

**Then**:
- 用默认配置
- 日志级别 WARNING
- 行为跟升级前一致

> **关键不变性**：默认行为零变化。新选项是叠加的，旧的 CLI 调用全部继续工作。

---

## 不变量

| 项 | 值 |
|---|---|
| 默认配置路径 | `xcli_data_dir()/config.yaml`（独立于 xavier）|
| 环境变量 | `XCLI_CONFIG` 覆盖 |
| 配置 schema | 见下方（YAML）|
| 不存在的配置 | 不报错（用默认）|
| 显式指定的配置不存在 | **报错**（fail fast）|
| 日志文件路径 | `xcli_data_dir()/x.log`（可配置）|
| 日志轮转 | v0.4.x 不做（单文件 append）；v0.5+ 加 rotation |
| 第三方依赖 | **零**（用 stdlib `logging` + 手写 YAML parser，**不**引 PyYAML）|

---

## 配置 schema（v0.4.x）

```yaml
# x-cli configuration
# 注释行（# 开头）会被忽略
# 不识别的 key 会被忽略（向前兼容）

# TODO 存储路径（默认 xcli_todo_dir()）
todo_dir: "C:\Users\X\AppData\Local\x-cli\todo"

# 密钥存储路径（默认 xcli_secrets_path()）
secrets_path: "C:\Users\X\AppData\Local\x-cli\secrets.json"

# 日志级别：DEBUG / INFO / WARNING / ERROR / CRITICAL（大小写不敏感）
log_level: WARNING

# 日志文件路径（null = 不写文件）
log_path: "C:\Users\X\AppData\Local\x-cli\x.log"
```

**未实现的字段**（v0.5+ 候选）：
- `proxy`（HTTP 代理）
- `api_endpoints`（LLM 端点覆盖）
- `colors`（是否启用 ANSI color）

---

## 退出码

| 码 | 含义 |
|----|------|
| 0 | 成功 |
| 2 | 参数错（`--config` 路径为空 / `--log-level` 值非法）|
| 5 | 配置错误（YAML 解析失败 / 配置文件不存在（当显式 --config 时））|
| 6 | **新增** — 日志系统初始化失败（权限 / IO 错）|

---

## 输出示例

### init 默认配置
```
$ x --config init
✅ 配置已写入：C:\Users\X\AppData\Local\x-cli\config.yaml

$ cat $env:LOCALAPPDATA\x-cli\config.yaml
# x-cli configuration (auto-generated by `x --config init`)
todo_dir: C:\Users\X\AppData\Local\x-cli\todo
secrets_path: C:\Users\X\AppData\Local\x-cli\secrets.json
log_level: WARNING
log_path: C:\Users\X\AppData\Local\x-cli\x.log
```

### --log-level DEBUG
```
$ x --log-level DEBUG todo list
[2026-06-21 18:30:00] [DEBUG] core.paths: xcli_todo_dir = C:\Users\X\AppData\Local\x-cli\todo
[2026-06-21 18:30:00] [DEBUG] core.storage: loading 4 active tasks
[2026-06-21 18:30:00] [INFO] x.main: starting x todo list
ID                 Name          Status      Priority   Deadline
─────────────────  ───────────  ──────────  ────────  ──────────
zhuxuejin-2026xia  助学金-下学期材料  ▶ in_progress  🔥 high    2026-06-22
...
```

### 加载自定义配置
```
$ XCLI_CONFIG=D:\my-config.yaml x todo list
[config] loaded: D:\my-config.yaml
[config] effective todo_dir: D:\my-projects\tasks
[config] effective log_level: DEBUG
...
```

---

## 与现有命令的关系

| 现有 | 新增 | 关系 |
|---|---|---|
| `x todo` 子命令 | `x --config init` | 新子命令（init 仅生成配置文件）|
| `XAVIER_TODO_DIR` env | `XCLI_CONFIG` + `todo_dir` 配置项 | 优先级：`XCLI_CONFIG` > `todo_dir` 配置 > `XAVIER_TODO_DIR`（向后兼容）|
| `XCLI_SECRETS_DIR` env | `secrets_path` 配置项 | 同上 |
| `print(...)` 输出 | `_log(level, msg)` | 新内部 API（替代散落的 print）|

**优先级规则**（重要）：
- `XAVIER_TODO_DIR` / `XCLI_SECRETS_DIR` 仍然 work（向后兼容）
- 但 `XCLI_CONFIG` 文件里的 `todo_dir` / `secrets_path` 优先级**更高**（更明确的用户意图）
- 配置文件不存在（且无 env）→ 用代码硬编码默认

---

## 不做（v0.4.x）

- ❌ 日志轮转（按日期 / 按大小）
- ❌ 嵌套配置 schema（带 section / include）
- ❌ 配置 validation（typo 检测）
- ❌ 配置热重载（运行中修改不生效）
- ❌ `x --log-level` 在子命令里单独覆盖（全局级别）
- ❌ `x config` 子命令（读 / 编辑 / diff）— 只做 `x --config init` 和 `x --config <path>` flag

---

*本文档是活文档，config / log-level 行为扩展同步更新。*
