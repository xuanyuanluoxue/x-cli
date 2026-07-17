# Distribution and WinGet Behavior

> 状态：已实现（v0.7.0）
> 范围：Python 包、Windows 独立 EXE、GitHub Release、WinGet portable 清单

## 功能：所有发行物使用同一个版本

### 场景：源码和 Python 包共享版本

Given 项目准备构建 v0.7.0

When setuptools 读取项目元数据，且用户运行 `x --version`

Then 两者都必须从 `core.version.__version__` 读取版本

And `pyproject.toml` 不得再维护第二个静态版本号

### 场景：错误版本 tag 阻止发布

Given 源码版本为 `0.7.0`

When GitHub Actions 由其他版本的 tag 触发

Then workflow 必须在创建 Release 之前失败

## 功能：Python 安装包完整

### 场景：wheel 包含 Web 子包和静态资源

Given 项目使用 setuptools 构建 wheel

When wheel 构建完成

Then wheel 必须包含 `core.web.handlers`

And 必须包含 `core/web/static/` 下的 HTML、CSS 和 JavaScript

And 运行时依赖仍为空

## 功能：Windows 用户无需安装 Python

### 场景：英文 Windows Runner 使用 UTF-8

Given Windows Runner 的系统代码页不能编码中文和 Emoji

When 发布脚本运行 pytest、Python 构建命令和 EXE 冒烟测试

Then 发布脚本必须为所有子进程启用 Python UTF-8 模式

And 完成后必须恢复调用者原有的编码环境变量

And EXE 冒烟测试必须显式按 UTF-8 捕获 stdout 和 stderr，不依赖 PowerShell 宿主代码页

### 场景：独立程序可直接运行

Given Windows x64 发行构建完成

When 用户运行 `x-windows-x86_64.exe --version`

Then 退出码为 0

And 输出 `x 0.7.0`

### 场景：独立程序包含插件和 Web 资源

Given Windows x64 发行构建完成

When 用户运行 `x-windows-x86_64.exe note --help`

Then 退出码为 0

And 输出 note 子命令帮助

When 用户启动 `x-windows-x86_64.exe web --no-browser`

Then Web 静态首页必须能被读取

## 功能：WinGet 安全安装和升级

### 场景：生成可提交的 portable 清单

Given 已构建不可变的 Windows x64 EXE

And 提供对应 GitHub Release HTTPS 下载地址

When 生成 WinGet 清单

Then ManifestVersion 为 `1.12.0`

And PackageIdentifier 为 `XuanyuanLuoxue.XCLI`

And InstallerType 为 `portable`

And Architecture 为 `x64`

And 命令别名为 `x`

And InstallerSha256 等于 EXE 的真实 SHA-256

### 场景：拒绝不可复现的清单输入

Given URL 不是 HTTPS、安装文件不存在、版本不是 `X.Y.Z`，或版本与源码不一致

When 尝试生成 WinGet 清单

Then 命令返回非零退出码

And 不生成可提交清单

### 场景：微软默认源尚未接受清单

Given GitHub Release 和清单已经准备好

But `microsoft/winget-pkgs` 尚未接受提交

When 用户阅读安装文档

Then 文档必须明确说明 WinGet 默认源暂不可用

And 不得声称 `winget install` 当前一定成功
