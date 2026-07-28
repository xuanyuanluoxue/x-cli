# x-cli Windows / WinGet 发行手册

> 面向维护者。普通用户安装方式见 `README.zh.md`。

## 发行边界

本仓库可以自动完成测试、wheel/sdist、Windows x64 EXE、SHA-256 和 WinGet
清单生成。创建 tag、push、GitHub Release，以及向
`microsoft/winget-pkgs` 提交 PR 都是外部发布动作。

没有得到仓库所有者明确授权时，**不要 commit、不要 push、不要创建
GitHub Release，也不要提交 WinGet PR**。

版本标签只能从已同步、工作树干净且 CI 通过的 `main` 提交创建。仓库不使用
单独的 `dev` 或 release 分支准备发行。

## 1. 准备隔离环境

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev,release]"
```

如果 pip 报 `Cannot connect to proxy`，先检查 Windows 系统代理是否指向已停止的
本地端口。只在确认需要直连时，为当前 PowerShell 临时设置：

```powershell
$env:NO_PROXY = "*"
$env:no_proxy = "*"
```

不要把环境相关的代理绕过写入仓库、系统级环境变量或最终用户安装脚本。

## 2. 版本检查

唯一版本来源是 `core/version.py`：

```powershell
.venv\Scripts\python.exe -c "from core.version import __version__; print(__version__)"
```

以下位置必须一致：

- `x --version`
- wheel 的 `Version` 元数据
- Git tag `vX.Y.Z`
- GitHub Release 下载 URL
- WinGet `PackageVersion`

GitHub Actions 会拒绝与源码版本不一致的 tag。

## 3. 本地构建和测试

完整发行验证：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build-windows.ps1
```

已经单独完成全量测试时，可跳过脚本内部的重复 pytest：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build-windows.ps1 -SkipTests
```

脚本会构建并验证：

- `dist/x_cli-X.Y.Z-py3-none-any.whl`
- `dist/x_cli-X.Y.Z.tar.gz`
- `dist/x-windows-x86_64.exe`
- `dist/x-windows-x86_64.exe.sha256`
- EXE 的 `--version`、`note --help` 和 Web 首页 HTTP 冒烟测试

## 4. 生成 WinGet 清单

```powershell
$Version = "0.8.0"
$Url = "https://github.com/xuanyuanluoxue/x-cli/releases/download/v$Version/x-windows-x86_64.exe"

.venv\Scripts\python.exe scripts\generate_winget_manifest.py `
  --version $Version `
  --installer dist\x-windows-x86_64.exe `
  --url $Url `
  --output dist\winget
```

生成器只接受：

- 与源码一致的数字 `X.Y.Z` 版本；
- 已存在的本地安装文件；
- 绝对 HTTPS 下载地址。

SHA-256 始终从实际 EXE 重新计算，不接受手工传值。

## 5. 严格验证清单

```powershell
winget validate --manifest `
  dist\winget\manifests\x\XuanyuanLuoxue\XCLI\0.8.0 `
  --disable-interactivity
```

必须看到 `Manifest validation succeeded.` 才能继续。建议再使用
`microsoft/winget-pkgs` 提供的 Windows Sandbox 测试流程验证实际安装、运行和卸载。

## 6. GitHub Release

`.github/workflows/release.yml` 有两种触发方式：

- 手动 `workflow_dispatch`：测试并构建 workflow artifact，绝不创建公开 Release。
- 推送 `vX.Y.Z` tag：版本校验通过后创建 GitHub Release。

Release 必须包含 EXE、SHA-256、wheel、sdist 和 WinGet 清单压缩包。Release
创建后再次确认清单 URL 可以匿名下载，且下载文件摘要与清单一致。

## 7. 提交到 WinGet 默认源

按照微软流程，将清单放入 `microsoft/winget-pkgs` 的：

```text
manifests/x/XuanyuanLuoxue/XCLI/X.Y.Z/
```

使用 `wingetcreate submit`，或者 fork 仓库后提交单独 PR。等待自动验证、杀毒扫描
和人工审核。微软接受前，README 必须保留“尚未进入 WinGet 默认源”的提示。

接受后验证：

```powershell
winget search --id XuanyuanLuoxue.XCLI -e
winget install --id XuanyuanLuoxue.XCLI -e
x --version
winget upgrade --id XuanyuanLuoxue.XCLI -e
winget uninstall --id XuanyuanLuoxue.XCLI -e
```

验证成功后，才可以移除 README 的未发布提示。
