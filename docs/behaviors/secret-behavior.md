# x secret 行为规格

> **目标读者**: 接续开发的 AI agent
> **范围**: `x secret <子命令>` 命令族，独立于 `<legacy-credentials-dir>/`，自管 JSON 数据库
> **对应测试**: `tests/test_secret.py`（单元）+ `tests/test_e2e_secret.py`（子进程）
> **状态**: 📋 P0 规划中（2026-06-21）

---

## 存储约定

**路径**（跨平台，stdlib 自动解析）：

| OS | 默认路径 |
|---|---|
| Windows | `%LOCALAPPDATA%\x-cli\secrets.json` |
| macOS/Linux | `$XDG_DATA_HOME/x-cli/secrets.json` → fallback `~/.local/share/x-cli/secrets.json` |

**覆盖**：环境变量 `XCLI_SECRETS_DIR` 指向文件（测试 / 自定义位置用）

**文件权限**：600（仅所有者读写）

**JSON schema**：

```json
{
  "version": "1.0",
  "secrets": [
    {
      "name": "minimax",
      "category": "接口密钥",
      "value": "sk-test1234",
      "note": "Migrated from 接口密钥.md",
      "created_at": "2026-06-21T12:34:56",
      "updated_at": "2026-06-21T12:34:56"
    }
  ]
}
```

字段约束：
- `name` — 唯一，必填，1-64 字符，**不**区分大小写（迁移保留原大小写）
- `category` — 默认 `"default"`，迁移时填入 `.md` 文件名（去 `.md`）
- `value` — 必填，可含换行（多行 `key:value` 格式）
- `note` — 可选，备注
- `created_at` / `updated_at` — ISO 8601 字符串

---

## 场景 1：list 列出所有密钥（不显示值）

**Given**:
- 测试 DB 含 3 个条目（minimax / openai / aliyun_ssh）

**When**:
- `x secret list`

**Then**:
- 退出码 0
- stdout 是表格：列 `Name / Category / Updated`，4 行（表头 + 3 数据）
- `value` 字段**绝不**出现在输出里
- 排序：按 `name` 字典序升序

---

## 场景 2：get <name> 输出 value

**Given**:
- DB 含 `minimax`，value = `sk-test1234`

**When**:
- `x secret get minimax`

**Then**:
- 退出码 0
- stdout 第一行 = `sk-test1234`（**仅** value，无前缀）
- stderr 含 `🔐 警告：密钥已输出到 stdout（可能被 shell 历史 / 日志捕获）`
- `note` / `category` / `created_at` **不**打印（除非 `--full`）

---

## 场景 3：get --full 输出完整元数据

**Given**:
- DB 含 `minimax`，category = `接口密钥`，note = `迁移自旧系统`

**When**:
- `x secret get minimax --full`

**Then**:
- 退出码 0
- stdout 表格：列 `Field / Value`，含 name / category / value / note / created_at / updated_at

---

## 场景 4：get <name> 不存在

**When**:
- `x secret get nonexistent`

**Then**:
- 退出码 3
- stderr 含 `❌ 密钥不存在：nonexistent`
- stdout 为空

---

## 场景 5：set <name> --value <v> 新增条目

**Given**:
- DB 不含 `minimax`

**When**:
- `x secret set minimax --value sk-test1234 --category 接口密钥`

**Then**:
- 退出码 0
- stdout 含 `✅ 密钥已创建：minimax`
- DB 新增条目（name=minimax, category=接口密钥, value=sk-test1234, created_at=今天）

---

## 场景 6：set <name> 缺 --value

**When**:
- `x secret set minimax`

**Then**:
- 退出码 2（argparse 拒绝）
- stderr 含 `the following arguments are required: --value`

---

## 场景 7：set <name> 已存在 → 拒绝

**Given**:
- DB 已含 `minimax`

**When**:
- `x secret set minimax --value sk-new`

**Then**:
- 退出码 4
- stderr 含 `❌ 密钥已存在：minimax（用 x secret update 修改）`

---

## 场景 8：update <name> --value 修改

**Given**:
- DB 含 `minimax`，value = `sk-old`

**When**:
- `x secret update minimax --value sk-new`

**Then**:
- 退出码 0
- stdout 含 `✅ 密钥已更新：minimax`
- DB 中 minimax.value = `sk-new`，updated_at = 今天

---

## 场景 9：update <name> 不存在

**When**:
- `x secret update nonexistent --value sk-x`

**Then**:
- 退出码 3
- stderr 含 `❌ 密钥不存在：nonexistent`

---

## 场景 10：rm <name> 删除

**Given**:
- DB 含 `minimax`

**When**:
- `x secret rm minimax`

**Then**:
- 退出码 0
- stdout 含 `✅ 密钥已删除：minimax`
- DB 中 minimax 不再存在

---

## 场景 11：rm <name> 不存在

**When**:
- `x secret rm nonexistent`

**Then**:
- 退出码 3
- stderr 含 `❌ 密钥不存在：nonexistent`

---

## 场景 12：search <keyword> 模糊匹配

**Given**:
- DB 含 `minimax` / `openai-prod` / `aliyun_ssh`

**When**:
- `x secret search api`

**Then**:
- 退出码 0
- stdout 表格：含 `openai-prod`（name 含 "api"），**不**含 `minimax`（值是 sk-test，但 name 不含）

**搜索范围**：`name` + `note`，**不**搜 `value`（避免密钥泄露到 grep）

---

## 场景 13：import --from <dir> 从 .md 迁移

**Given**:
- 临时目录有 2 个 .md 文件：
  - `接口密钥.md` 含 section `minimax`（text 块：`api_key: sk-x`）
  - `令牌.md` 含 section `openai`（text 块：`token: tk-y`）
- DB 已含 `minimax`（**重复**）

**When**:
- `x secret import --from <tmp_dir>`

**Then**:
- 退出码 0
- stdout 含：
  ```
  📥 迁移完成：导入 1 条，跳过 1 条（重复）
  ```
- DB 中 `minimax`（原值不变），`openai` 新增（category=`令牌`）
- 旧 .md 文件**保留**在 `<tmp_dir>`（不删）

---

## 场景 14：import --from <dir> 目录不存在

**When**:
- `x secret import --from /nonexistent/path`

**Then**:
- 退出码 5
- stderr 含 `❌ 源目录不存在：/nonexistent/path`

---

## 场景 15：export 备份到 JSON

**Given**:
- DB 含 2 个条目

**When**:
- `x secret export`

**Then**:
- 退出码 0
- stdout 含 `✅ 已备份 N 条到 <path>`
- 备份文件：`<DB 目录>/secrets-backup-YYYYMMDD-HHMMSS.json`
- 备份格式与 DB 相同（可直接覆盖恢复）

---

## 场景 16：<空> 显示用法

**When**:
- `x secret`（无子命令）

**Then**:
- 退出码 0
- stdout 显示 usage + 7 个子命令（list / get / set / update / rm / search / import / export）

---

## 场景 17：`x secret --help`

**Then**:
- 退出码 0
- stdout 含 usage + 全局选项 + 子命令说明

---

## 不变量

| 项 | 值 |
|---|---|
| **真实 DB 路径** | `%LOCALAPPDATA%\x-cli\secrets.json`（**永不触碰**，测试走临时目录） |
| **覆盖** | 环境变量 `XCLI_SECRETS_DIR` |
| **文件权限** | 600（Windows 用 ACL）|
| **加密** | MVP 不加密（明文 + 文件权限保护） |
| **依赖** | **零**第三方库（只 stdlib `json` / `pathlib` / `os` / `datetime`）|
| **list 不显示 value** | 硬性约束（避免 `x secret list > log.txt` 泄露）|
| **get 永远带警告** | 硬性约束（不管是否 tty）|
| **search 不搜 value** | 硬性约束（避免 grep 撞到）|

---

## 退出码速查

| 码 | 含义 |
|----|------|
| 0 | 成功 |
| 2 | 参数错（argparse 拒绝）|
| 3 | 不存在 |
| 4 | 已存在（set 时）|
| 5 | DB 错（JSON 损坏 / 权限 / 迁移源不存在）|

---

## 不做（v0.3.0）

- ❌ 加密（master password / Fernet）
- ❌ 子命令缩写（`x s l`）
- ❌ TUI（rich / textual）
- ❌ 标签 / 分组（用 `category` 替代）
- ❌ 自动备份到云端（用 `export` 手动备份）

---

*本文档是活文档，命令扩展同步更新。*