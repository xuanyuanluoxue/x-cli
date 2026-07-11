# x todo 数据导出 行为规格（v0.5 Phase E）

> **对应命令**：`x todo export`
> **新增 flag**：`--format json|csv|md`、`--output <path>`、`--all`（包含 archived）
> **数据格式**：
> - JSON: 完整 frontmatter + body（dump_frontmatter 输出）
> - CSV: 扁平表，id / name / status / priority / deadline / time / tags / parent / archived_at
> - MD: 人类可读表格
> **来源**：[PLAN-v0.5.md §2.4.3 + §3.4](../../../PLAN-v0.5.md)
>
> **覆盖范围**：
> - 3 种格式导出
> - --all 包含 archived
> - --output 自定义路径（默认 stdout / `<xcli_data_dir>/exports/<timestamp>.<fmt>`）
> - CSV 多值字段用 `;` 分号分隔
> - 错误路径

---

## 场景 1：`export --format json` 到 stdout

**Given**：
- 仓库有 2 个 active 任务

**When**：
- 运行 `x todo export --format json`

**Then**：
- 退出码：`0`
- stdout 输出合法 JSON 数组
- 数组每个元素含 `id / name / status / priority / frontmatter + body`

---

## 场景 2：`export --format json --output file.json`

**When**：
- 运行 `x todo export --format json --output D:\Temp\tasks.json`

**Then**：
- 退出码：`0`
- 输出：`"✅ 已导出 2 个任务到 D:\Temp\tasks.json"`
- 文件存在且为合法 JSON 数组

---

## 场景 3：`export --format csv` 扁平表

**Given**：
- 任务 A：`tags=["a", "b"]`, `priority="high"`, `deadline="2026-07-01"`

**When**：
- 运行 `x todo export --format csv`

**Then**：
- 退出码：`0`
- stdout 是 CSV，header 行含 `id,name,status,priority,deadline,tags,...`
- 任务 A 行：`...,high,2026-07-01,a;b,...`（tags 用 `;` 分隔）

---

## 场景 4：`export --format md` Markdown 表格

**When**：
- 运行 `x todo export --format md`

**Then**：
- 退出码：`0`
- stdout 是 markdown 表格（`| ... |` 格式）
- 列与 CSV 类似

---

## 场景 5：`export --all` 包含 archived

**Given**：
- 1 active + 1 archived 任务

**When**：
- 运行 `x todo export --format json --all`

**Then**：
- 退出码：`0`
- 数组含 2 个任务（active + archived）

---

## 场景 6：默认输出（不传 --format）

**When**：
- 运行 `x todo export`

**Then**：
- 退出码：非 0（如 `2`）
- 输出：`"❌ 必须指定 --format (json|csv|md)"`

---

## 场景 7：`export --format invalid`

**When**：
- 运行 `x todo export --format yaml`

**Then**：
- 退出码：非 0（如 `2`）
- 输出：`"❌ 无效的 format：yaml（支持：json / csv / md）"`

---

## 场景 8：`export --output` 父目录不存在（错误）

**When**：
- 运行 `x todo export --format json --output D:\no-such-dir\tasks.json`

**Then**：
- 退出码：非 0（如 `5`）
- 输出：`"❌ 父目录不存在：D:\no-such-dir"`

---

*本文件由 v0.5 Phase E 任务生成（2026-06-30），覆盖 3 种格式导出 + --all + --output*