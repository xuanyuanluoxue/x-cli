# 命令参考

> **目标读者**：使用 x-cli 的人类（包括未来的你）  
> **说明**：本文档列出所有命令的完整参考

---

## 1. 总入口：`x`

### 1.1 用法

```bash
x <子命令> [选项]
```

### 1.2 全局选项

| 选项 | 说明 |
|------|------|
| `-v, --version` | 显示版本号 |
| `-h, --help` | 显示帮助信息 |
| `--config <路径>` | 指定配置文件（默认 `~/.xavier/config.yaml`）|
| `--log-level <级别>` | 设置日志级别（DEBUG/INFO/WARNING/ERROR）|

### 1.3 示例

```bash
# 显示版本号
x --version

# 显示帮助信息
x --help

# 指定配置文件
x --config /path/to/config.yaml todo list

# 设置日志级别为 DEBUG
x --log-level DEBUG todo add "测试任务"
```

---

## 2. `x todo` — TODO 管理

### 2.1 子命令概览

| 子命令 | 说明 | 参数 |
|--------|------|------|
| `x todo list` | 列出任务 | `--status` / `--priority` / `--tag` |
| `x todo add <名称>` | 添加任务 | `--priority` / `--deadline` / `--tags` |
| `x todo update <id>` | 更新任务 | `--status` / `--priority` / `--deadline` |
| `x todo archive <id>` | 归档任务 | `--reason` |
| `x todo stats` | 统计信息 | 无 |

### 2.2 `x todo list` — 列出任务

**用法**：
```bash
x todo list [选项]
```

**选项**：
| 选项 | 说明 |
|------|------|
| `--status <状态>` | 按状态过滤（pending/in_progress/archived）|
| `--priority <优先级>` | 按优先级过滤（high/medium/low）|
| `--tag <标签>` | 按标签过滤 |
| `--all` | 显示所有任务（包括已归档）|

**示例**：
```bash
# 列出所有进行中的任务
x todo list --status in_progress

# 列出所有高优先级的任务
x todo list --priority high

# 列出所有任务（包括已归档）
x todo list --all
```

**输出格式**（表格）：
```
ID      Name                Status      Priority    Deadline
kemu1   科目一模拟考         pending     high        2026-08-31
kemu2   自主实习材料         in_progress medium      -
```

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
| 选项 | 说明 | 默认值 |
|------|------|--------|
| `--priority <优先级>` | 优先级（high/medium/low）| `medium` |
| `--deadline <日期>` | 截止日期（YYYY-MM-DD）| 无 |
| `--tags <标签>` | 标签（逗号分隔）| 无 |

**示例**：
```bash
# 添加任务（最简）
x todo add "科目一模拟考"

# 添加任务（完整参数）
x todo add "科目一模拟考" --priority high --deadline 2026-08-31 --tags 驾照,暑假
```

**输出**：
```
✅ 任务已创建：科目一模拟考（ID: kemu1）
```

---

### 2.4 `x todo update <id>` — 更新任务

**用法**：
```bash
x todo update <id> [选项]
```

**必填参数**：
| 参数 | 说明 |
|------|------|
| `<id>` | 任务 ID（必填）|

**选项**：
| 选项 | 说明 |
|------|------|
| `--status <状态>` | 更新状态（pending/in_progress/archived）|
| `--priority <优先级>` | 更新优先级（high/medium/low）|
| `--deadline <日期>` | 更新截止日期（YYYY-MM-DD）|
| `--tags <标签>` | 更新标签（逗号分隔）|

**示例**：
```bash
# 更新任务状态
x todo update kemu1 --status in_progress

# 更新任务优先级和截止日期
x todo update kemu1 --priority high --deadline 2026-07-01
```

**输出**：
```
✅ 任务已更新：科目一模拟考（ID: kemu1）
```

---

### 2.5 `x todo archive <id>` — 归档任务

**用法**：
```bash
x todo archive <id> [选项]
```

**必填参数**：
| 参数 | 说明 |
|------|------|
| `<id>` | 任务 ID（必填）|

**选项**：
| 选项 | 说明 | 默认值 |
|------|------|--------|
| `--reason <原因>` | 归档原因 | `done` |

**示例**：
```bash
# 归档任务（默认原因：done）
x todo archive kemu1

# 归档任务（指定原因）
x todo archive kemu1 --reason "已完成"
```

**输出**：
```
✅ 任务已归档：科目一模拟考（ID: kemu1）
```

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

总任务数：10
- pending：3
- in_progress：5
- archived：2

优先级分布：
- high：2
- medium：5
- low：3

即将到期（7 天内）：1
```

---

## 3. `x skill` — 技能管理（未来）

### 3.1 子命令概览

| 子命令 | 说明 | 参数 |
|--------|------|------|
| `x skill list` | 列出已安装技能 | 无 |
| `x skill install <名称>` | 安装技能 | `<名称>` |
| `x skill update <名称>` | 更新技能 | `<名称>` |
| `x skill remove <名称>` | 删除技能 | `<名称>` |

---

## 4. `x system` — 系统工具（未来）

### 4.1 子命令概览

| 子命令 | 说明 | 参数 |
|--------|------|------|
| `x system backup` | 备份 `~/.xavier/` | `--dry-run` |
| `x system sync` | 同步到云端（rclone）| `--target <云端>` |
| `x system health` | 检查系统健康状态 | 无 |
| `x system log` | 查看日志 | `--level <级别>` |

---

## 5. 缩写支持（未来）

### 5.1 子命令缩写

**MVP 阶段**：不支持缩写（保持简单）

**后期扩展**：支持子命令缩写

```bash
# 完整命令
x todo list

# 缩写（未来）
x t l
```

### 5.2 自动缩写（未来）

**想法**：自动匹配唯一前缀

```bash
# 如果只有 "todo" 以 "t" 开头，则自动匹配
x t list

# 如果有多个匹配（如 "todo" 和 "tag"），报错提示
x t list
# 错误： ambiguous prefix: t (todo, tag)
```

---

## 6. Tab 补全（未来）

### 6.1 启用 Tab 补全

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

### 6.2 补全示例

```bash
x <TAB><TAB>
todo    skill    system

x todo <TAB><TAB>
list    add     update  archive  stats

x todo add --<TAB><TAB>
--priority    --deadline    --tags
```

---

*本文档是活文档，随命令集扩展更新*
