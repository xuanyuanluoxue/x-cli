# Release & Packaging Guide（v0.6.0+）

> **目标读者**：想给 x-cli 打包成可执行分发给**自己**用的人
> **当前状态**：v0.6.0 收口，实装 PyInstaller 打包脚本
> **不**面向生产分发（个人用，不签名 / 不 notarize / 不做 MSI / DMG）

---

## 1. 设计目标

x-cli 的打包策略遵循三个原则：

1. **运行时 stdlib-only**：x-cli 本身不依赖任何第三方库。打包是 **opt-in** 步骤，dev 用 venv 直接跑就行
2. **PyInstaller 当依赖**：构建步骤（不是运行时）需要 PyInstaller，所以不写进 `pyproject.toml`，而是 `pip install` 一次
3. **跨平台提示**：`build.py --platform {win,mac,linux}` 接受提示，但实际必须在目标 OS 上跑（PyInstaller 不支持交叉编译）

**为什么 PyInstaller**？
- 生态成熟（`x.py` 这种纯 stdlib + 单 entry 的项目 PyInstaller 打包稳定）
- 支持 onefile（个人用方便分发）
- 不需要额外运行时（不像 .NET / JVM）

**为什么不引 nuitka / py2exe / shiv / pex**？
- 个人用，PyInstaller 够了
- 一致性：一个打包工具管所有平台

---

## 2. 跨平台约束

### 2.1 产物

| OS | 产物 | 路径（默认）|
|---|---|---|
| Windows 10+ | `x.exe` | `%LOCALAPPDATA%\x-cli\bin\x.exe` |
| macOS | `x` | `~/.local/share/x-cli/bin/x`（或 `$XDG_DATA_HOME/x-cli/bin/x`）|
| Linux | `x` | 同 macOS |

**注意**：macOS 上 `$XDG_DATA_HOME` 通常**未设置**（macOS 不遵循 XDG），所以默认走 `~/.local/share/`。如果用户偏 Apple 原生 `~/Library/Application Support/`，可以 export `XDG_DATA_HOME`（PyInstaller 脚本接受这个变量）。

### 2.2 跨平台构建限制

**PyInstaller 不支持交叉编译**。要 build 三平台的产物，需要三台机器（或三套 CI runner）：

| 目标 | 必须在 | CI runner 推荐 |
|---|---|---|
| Windows | Windows | `windows-latest` |
| macOS | macOS | `macos-latest` |
| Linux | Linux | `ubuntu-latest` |

`--platform` flag **不切换**构建目标——它只是一个 build-time 提示，让用户记录"这次 build 打算给谁用"。

### 2.3 输出位置

build.py 故意不输出到 `dist/`（默认 PyInstaller 行为），而是：
- 产物 → `<xcli_data_dir>/bin/`（用户数据目录，**不污染**仓库）
- work cache → `<repo>/build/`（可 `--clean` 清，gitignored）
- spec file → `<repo>/build/x.spec`（每次 build 重新生成）

---

## 3. `release/build.py` 用法

### 3.1 前置：装 PyInstaller

**仅一次**：

```bash
# Windows
.venv\Scripts\python.exe -m pip install pyinstaller

# macOS / Linux
.venv/bin/python -m pip install pyinstaller
```

**为什么不在 pyproject.toml**？因为 x-cli 的运行时依赖保持 `dependencies = []`。PyInstaller 是构建工具（不是运行时）。

### 3.2 基本 build

```bash
# 当前 OS
.venv\Scripts\python.exe release\build.py

# 输出（成功时）：
#   ✅ 构建完成：C:\Users\X\AppData\Local\x-cli\bin\x.exe  (10.3 MB)
#   测试：C:\Users\X\AppData\Local\x-cli\bin\x.exe --version
```

### 3.3 加 `--clean` 清缓存

```bash
.venv\Scripts\python.exe release\build.py --clean
# 会先删 <repo>/build/ 和 <repo>/dist/（如果存在），然后重 build
```

适用于：
- 改了 `x.py` 入口逻辑
- 升了 PyInstaller 版本
- 之前 build 失败留下脏状态

### 3.4 提示目标平台

```bash
# 在 macOS 上为 Linux build？不行，必须在 Linux 上跑。
# 但 --platform 可加注解：
.venv\Scripts\python.exe release\build.py --platform linux
# 输出（如果当前是 macOS）：
#   ⚠️  提示：你在 'linux' 目标上跑，但当前 OS 是 'mac'。PyInstaller 不支持交叉编译 —— 请在目标 OS 上重跑。
```

### 3.5 build 完跑一遍 sanity

```bash
# 验证版本
"%LOCALAPPDATA%\x-cli\bin\x.exe" --version
# 期望：x-cli v0.6.0

# 验证帮助
"%LOCALAPPDATA%\x-cli\bin\x.exe" --help
# 期望：含 todo / secret / web 三个子命令

# 跑一个真命令
"%LOCALAPPDATA%\x-cli\bin\x.exe" todo list
```

---

## 4. 故障排查

### 4.1 `❌ PyInstaller 未安装`

**症状**：
```
❌ PyInstaller 未安装。
   在项目 venv 中跑：
       .venv\Scripts\python.exe -m pip install pyinstaller
   （Unix 上：.venv/bin/python -m pip install pyinstaller）
```

**修**：
```bash
.venv\Scripts\python.exe -m pip install pyinstaller
```

### 4.2 `ModuleNotFoundError: No module named 'X'` 在 build 时

**症状**：
```
ModuleNotFoundError: No module named 'foo'
```

**原因**：
- v0.6.0 x-cli 本身 stdlib-only（`dependencies = []`）
- 如果你引了第三方库，PyInstaller 通常能自动发现，但偶尔漏（特别是动态 import）

**修**：
1. 检查 `x.py` 和 `plugins/*.py` 顶部 import
2. 如果是 dynamic import（`__import__("foo")`），在 `build.py` 加 `--hidden-import foo`
3. 或者用 `release/x.spec` 显式声明（PyInstaller 首次 build 生成的 spec 文件）

### 4.3 Windows 杀软报毒

**症状**：build 完双击 `x.exe` 弹"Windows Defender SmartScreen 阻止了无法识别的应用"或"木马"。

**原因**：PyInstaller 打包的 onefile 二进制经常被杀软误报（因为压缩包内嵌 Python 解释器和字节码，杀软启发式匹配）。

**修**：
- 个人用：选"仍要运行"即可
- 长期用：给 `x.exe` 加 Windows Defender 排除项：
  ```powershell
  Add-MpPreference -ExclusionPath "$env:LOCALAPPDATA\x-cli\bin"
  ```
- 不推荐代码签名（个人用成本不划算）

### 4.4 macOS "cannot be opened because the developer cannot be verified"

**症状**：build 完双击 `x` 弹"无法打开，因为无法验证开发者"。

**修**：
```bash
# 一次性
xattr -d com.apple.quarantine ~/.local/share/x-cli/bin/x
```

或者右键 → 打开 → 确认。

### 4.5 Linux `Permission denied` 或 `libpython not found`

**症状**：
```
x: error while loading shared libraries: libpython3.14.so.1.0: cannot open shared object file
```

**原因**：PyInstaller 打的 binary 是动态链接到系统 Python 的（不是完全静态）。

**修**（在 Linux 上）：
- 用 `ldd x` 看依赖
- 装 `libpython3.14`（或对应版本）：`sudo apt install libpython3.14`
- 或者改 `--onefile` 模式（其实默认就是 onefile，可能没生效，验证 build.py 调用）

**修**（在 macOS 上）：
- macOS 自带 Python 框架，应该没问题
- 如果用 brew 装的 Python，确保 homebrew 的 openssl 已链接

### 4.6 启动慢（首次运行 1-2 秒）

**原因**：PyInstaller onefile 默认每次启动都自解压到临时目录。

**修**（如果觉得慢）：
- 改 `release/build.py` 用 `--onedir` 而不是 `--onefile`（产物是文件夹，不是单文件）
- 接受：onefile 的"启动慢"对个人 CLI 工具不是问题（一次启动 1 秒用户感知不强）

### 4.7 build 后产物大小

典型大小（v0.6.0 实测）：

| 平台 | onefile 大小 | 备注 |
|---|---|---|
| Windows | ~10 MB | Python 3.14 + stdlib + 项目代码 |
| macOS | ~12 MB | 同上 + frameworks |
| Linux | ~11 MB | 同上 |

如果太大，常见原因：
- 引了不需要的库（用 `--exclude-module`）
- 没 UPX 压缩（加 `--upx-dir /path/to/upx` 可减 30%）

---

## 5. 不在范围内的特性

- ❌ **代码签名**（macOS codesign / Windows Authenticode）— 个人用不需要
- ❌ **Notarization**（Apple 公证）— 跳过
- ❌ **自动更新**（x-cli 不会有新版本检查）— 个人用手动 git pull
- ❌ **MSI / DMG / .deb / .rpm 安装包**— PyInstaller 产物直接用
- ❌ **CI 自动发布到 GitHub Releases**— 暂不实现，手动分发即可
- ❌ **交叉编译**（在 Linux 上 build Windows .exe）— PyInstaller 不支持

---

## 6. 替代方案（如果 PyInstaller 哪天不行）

| 方案 | 优点 | 缺点 | 个人用评估 |
|---|---|---|---|
| **PyInstaller**（当前）| 生态成熟，onefile | 杀软误报，体积大 | ✅ 够用 |
| **Nuitka** | 真编译（CPython → C），更快 | 配置复杂，构建慢 | 备选 |
| **shiv** | 简单（zip 包含 site-packages）| 仍依赖系统 Python | 不适合 onefile |
| **pex** | 同 shiv，更细粒度 | 同上 | 不适合 onefile |
| **PyOxidizer** | 比 PyInstaller 更现代 | 文档少，构建工具链复杂 | 备选 |

当前 v0.6.0 选 PyInstaller（最稳）。如果将来出问题（杀软疯狂报毒等），切 Nuitka 即可——`release/build.py` 改个 wrapper 就行。

---

*Last updated: 2026-06-28*
