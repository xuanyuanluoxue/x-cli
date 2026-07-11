# Design: x web 自动 Token URL 注入（opt-in, 默认关闭）

**日期**：2026-06-28
**作者**：x-cli 后端 agent
**分支**：`feature/web-verify`
**状态**：✅ 用户已批准（"a + 用户可以关闭 + 默认关闭"）

---

## 0. 背景

### 当前流程

```
$ x web start
⏳ 启动 x web server...
   地址：http://127.0.0.1:8421
   Token: a3b7c9e1f2d4...
   已在浏览器打开
   请在浏览器输入上面的 Token
   按 Ctrl+C 停止
```

**痛点**：每次启动 token 都变（32 字节 random），用户要从终端**复制粘贴**到浏览器 → 摩擦大。

### 用户反馈（2026-06-28）

> "填写 token 太麻烦了"

但**不要完全去掉 token**（任何人能访问 127.0.0.1:8421 都能读 secret，太危险）。

---

## 1. 目标 & 非目标

### 1.1 目标

- ✅ **消除复制粘贴**：浏览器自动开 + URL 带 `?token=xxx` + 前端自动 setToken
- ✅ **保留 32 字节 random 安全**：token 仍然每次启动生成
- ✅ **URL 即时清空**：前端拿到 token 后立即 `history.replaceState` 清掉 URL 里的 token（防浏览器历史 / 同步泄露）
- ✅ **opt-in + 默认关闭**：用户**显式** `--auto-token-url` 才启用；不传 = 现状（手动输入）
- ✅ **测试 + e2e**

### 1.2 非目标

- ❌ 不完全去掉 token（**会**有 127.0.0.1:8421 暴露风险）
- ❌ 不把 token 写到 config.yaml（**会**让 token 永久化，被偷一次永久）
- ❌ 不改 API 契约（`docs/web-api.md`）
- ❌ 不改后端鉴权（`X-Web-Token` 头）
- ❌ 不改前端架构（仅 `login.js` 一处加 `?token=` 解析）

---

## 2. 设计

### 2.1 CLI 改动（`plugins/web.py`）

**新增 flag**：

```python
parser.add_argument(
    "--auto-token-url",
    "-A",
    action="store_true",
    help=(
        "自动把 token 注入到浏览器 URL（?token=xxx），"
        "前端自动填 + 立即清 URL。"
        "⚠️ opt-in：默认关闭（防 URL 泄露到浏览器历史/同步）。"
    ),
)
```

**改动**：`webbrowser.open(url)` 行：

```python
# 原 (无 flag)
webbrowser.open(url)

# 新（按 flag 决定）
if args.auto_token_url:
    webbrowser.open(f"{url}?token={token}")
else:
    webbrowser.open(url)
```

**设计选择**：
- 短选项 `-A`（Auto-URL 的 A）
- `action="store_true"`（无值）
- 默认 False（opt-in 语义）

### 2.2 前端改动（`core/web/static/js/views/login.js`）

**在 token 输入框 mount 之前**（行 170 之前），加 URL `?token=` 解析：

```js
// 1. 优先从 URL 拿 token（opt-in 模式：CLI 启动了 --auto-token-url）
const urlToken = new URLSearchParams(window.location.search).get("token");
if (urlToken) {
    setToken(urlToken);
    // 2. 立即清掉 URL（防历史/同步泄露）
    const cleanUrl = window.location.pathname + window.location.hash;
    window.history.replaceState({}, document.title, cleanUrl);
    // 3. 验证 token + 跳主页
    try {
        await api.listTasks();
        window.location.hash = "#tasks";
        return;
    } catch (e) {
        // token 无效（server 重启过）→ 清 localStorage + 显示输入框
        clearToken();
    }
}
```

**关键安全点**：
- **第 1 步**优先（localStorage 之前）—— 因为 URL token 是新启动的，更权威
- **`history.replaceState` 第 2 步**——URL 立刻清掉，浏览器历史只看到无 token URL
- **`await api.listTasks()` 第 3 步**——验证 token 有效（server 重启后旧 token 会失效），无效就 fallback 到输入框

### 2.3 用户体验对比

#### 默认（无 flag）：手动输入（现状）

```bash
$ x web start
⏳ 启动 x web server...
   地址：http://127.0.0.1:8421
   Token: a3b7c9e1f2d4...
   已在浏览器打开
   请在浏览器输入上面的 Token   ← 复制粘贴
   按 Ctrl+C 停止
```

浏览器：
1. 自动开 `http://127.0.0.1:8421/`
2. 显示 token 输入框
3. 用户从终端复制 `a3b7c9e1f2d4...` 粘贴
4. 跳 #tasks

#### `--auto-token-url` 模式：自动填

```bash
$ x web start --auto-token-url   # 或 -A
⏳ 启动 x web server...
   地址：http://127.0.0.1:8421
   Token: a3b7c9e1f2d4...
   已在浏览器打开（URL 含 ?token=...，浏览器自动填后清 URL）
   按 Ctrl+C 停止
```

浏览器：
1. 自动开 `http://127.0.0.1:8421/?token=a3b7c9e1f2d4...`
2. 前端拿到 token → 存 localStorage → `history.replaceState` 清 URL
3. 跳 #tasks（**用户感知 0 步操作**）

**URL 在浏览器历史里的样子**（无 token）：

```
http://127.0.0.1:8421/#tasks    ← 看不到 token
```

---

## 3. 测试

### 3.1 单元测试（`tests/test_web_api.py` 或新文件）

```python
def test_web_auto_token_url_flag_default_false():
    """默认（无 --auto-token-url）→ 自动开浏览器时 URL 不带 ?token=。"""
    # mock webbrowser.open，验证传入的 URL 不含 ?token=
    pass

def test_web_auto_token_url_flag_enabled():
    """加 --auto-token-url → 自动开浏览器时 URL 含 ?token=xxx。"""
    # mock webbrowser.open，验证传入的 URL 是 f"{url}?token={token}"
    pass

def test_web_no_browser_disables_token_url():
    """--no-browser 与 --auto-token-url 同时给：--no-browser 优先（不开浏览器）"""
    pass
```

### 3.2 e2e（`tests/test_e2e_web.py`，如不存在则新建）

```python
def test_e2e_x_web_with_auto_token_url_in_help(x_path, todo_dir):
    """--auto-token-url 必须在 x web --help 出现。"""
    # 跳过 --no-browser 跑 x web --help
    pass
```

### 3.3 浏览器自动化测试（可选，超出 scope）

用 `autoglm-browser-agent` 跑 headless 浏览器，验证：
1. URL `?token=` 出现在 history 之前
2. `history.replaceState` 后 URL 不含 `?token=`
3. 跳 #tasks 成功

**不强制**（取决于工具有无 + 跑时间）；curl 测后端 + 静态文件 + mock webbrowser.open 已足够。

---

## 4. 风险 & 缓解

| 风险 | 等级 | 缓解 |
|---|---|---|
| URL token 泄露到浏览器历史 | 中 | `history.replaceState` 第 1 时间清掉 |
| URL token 泄露到 referrer | 极低 | 127.0.0.1 内部 URL，无外站 referrer |
| Token 失效（server 重启） | 低 | 前端 catch → clearToken + fallback 输入框 |
| 用户误开 --auto-token-url | 低 | help 文本明确"⚠️ opt-in" |
| 与同事的 frontend worktree 冲突 | 低 | login.js 改动最小化（仅加 ~10 行） |
| `--no-browser` + `--auto-token-url` 同时给（v0.6.0 addendum）| 低 | 启动时 stderr 警告（不强制） |

### 4.1 Addendum（2026-06-28 用户反馈后加）

**问题**：`x web --no-browser --auto-token-url` 时 `--auto-token-url` 静默无效（不开浏览器 = URL 注入无意义）。用户开两个 flag 后**没看到任何提示**，困惑。

**解决**（选 A 方案：stderr 警告，不动用户意图）：

- `plugins/web.py:run()` 检测到 `--no-browser` + `--auto-token-url` 同时给时，打印 2 行 stderr 提示
- 实现：`if parsed.no_browser and parsed.auto_token_url: print(...)` 在 `if not parsed.no_browser` 块之前
- 消息：
  ```
  ⚠️  --auto-token-url 在 --no-browser 模式下静默无效
     （不开浏览器 = URL 注入无意义；要生效请去掉 --no-browser）
  ```
- 不退出 / 不报错（保留用户选择 + 尊重 `--no-browser` 意图）
- 测：3 个 `_open_browser` helper test（test_open_browser_*），覆盖默认 / 自动 / 异常静默

---

## 5. 实施步骤

| Step | 操作 | Commit 前缀 |
|---|---|---|
| 1 | 写本 spec | `docs(superpowers/specs)` |
| 2 | `plugins/web.py` 加 `--auto-token-url` flag + webbrowser.open 改 | `feat(web)` |
| 3 | `core/web/static/js/views/login.js` 加 URL `?token=` 解析 + 清 URL | `feat(web-frontend)` |
| 4 | `tests/test_web_api.py` 加 3 个 unit test | `test(web)` |
| 5 | `tests/test_e2e_web.py` 加 1 个 e2e（help 文本含 flag）| `test(e2e)` |
| 6 | 跑全量 + push feature/web-verify | — |

**commit 边界**：
- 步骤 2-3 跨前端 / 后端，按 CONTRIBUTING.md §2.3 后端先合 / 前端再合。
- 但**这次都在同一个 feature/web-verify 分支**（验证任务多方向），最终一个 PR 即可。

---

## 6. 关联

- **handoff**：`docs/prompts/web-frontend-handoff.md`（前后端边界 + 硬约束）
- **AGENTS.md §4.4**：Git 分支策略（这次用 `feature/web-verify` 分支）
- **CONTRIBUTING.md §7**：后端插件契约（plugins/web.py 必须 register 暴露 flag）
- **本次任务基线**：v0.6.0 dev 分支已含 frontend + backend merge（32aa98b / 4ba6bb5）

---

*Last updated: 2026-06-28*
