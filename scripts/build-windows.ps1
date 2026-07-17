[CmdletBinding()]
param(
    [switch]$SkipTests
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-CapturedUtf8Process {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [string[]]$ProcessArguments = @()
    )

    $StartInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $StartInfo.FileName = $Executable
    $StartInfo.Arguments = $ProcessArguments -join " "
    $StartInfo.UseShellExecute = $false
    $StartInfo.CreateNoWindow = $true
    $StartInfo.RedirectStandardOutput = $true
    $StartInfo.RedirectStandardError = $true
    $StartInfo.StandardOutputEncoding = [System.Text.Encoding]::UTF8
    $StartInfo.StandardErrorEncoding = [System.Text.Encoding]::UTF8

    $Process = [System.Diagnostics.Process]::new()
    $Process.StartInfo = $StartInfo
    [void]$Process.Start()
    $Stdout = $Process.StandardOutput.ReadToEnd()
    $Stderr = $Process.StandardError.ReadToEnd()
    $Process.WaitForExit()
    $Result = [PSCustomObject]@{
        ExitCode = $Process.ExitCode
        Stdout = $Stdout
        Stderr = $Stderr
    }
    $Process.Dispose()
    return $Result
}

function Test-PackagedWebUi {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [Parameter(Mandatory = $true)][string]$RepositoryRoot
    )

    # PyInstaller one-file executables may replace the launcher with a child
    # process. Remember pre-existing processes so cleanup only stops the
    # instances created by this smoke test.
    $ExistingExecutableProcessIds = @(
        Get-CimInstance Win32_Process |
            Where-Object { $_.ExecutablePath -eq $Executable } |
            ForEach-Object { $_.ProcessId }
    )

    $Listener = [System.Net.Sockets.TcpListener]::new(
        [System.Net.IPAddress]::Loopback,
        0
    )
    $Listener.Start()
    $Port = ([System.Net.IPEndPoint]$Listener.LocalEndpoint).Port
    $Listener.Stop()

    $LogDir = Join-Path $RepositoryRoot "build\release-web-smoke"
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
    $StdoutLog = Join-Path $LogDir "stdout.log"
    $StderrLog = Join-Path $LogDir "stderr.log"
    $Arguments = @(
        "web",
        "--host", "127.0.0.1",
        "--port", $Port.ToString(),
        "--token", "release-smoke-token",
        "--no-browser"
    )

    $WebProcess = Start-Process `
        -FilePath $Executable `
        -ArgumentList $Arguments `
        -PassThru `
        -WindowStyle Hidden `
        -RedirectStandardOutput $StdoutLog `
        -RedirectStandardError $StderrLog
    try {
        $Ready = $false
        for ($Attempt = 0; $Attempt -lt 40; $Attempt++) {
            $WebProcess.Refresh()
            if ($WebProcess.HasExited) {
                $Details = Get-Content -LiteralPath $StderrLog -Raw -ErrorAction SilentlyContinue
                throw "Packaged Web server exited before smoke test: $Details"
            }
            try {
                $Response = Invoke-WebRequest `
                    -Uri "http://127.0.0.1:$Port/" `
                    -UseBasicParsing `
                    -TimeoutSec 2
                if (
                    $Response.StatusCode -eq 200 -and
                    $Response.Content -match "<title[^>]*>"
                ) {
                    $Ready = $true
                    break
                }
            }
            catch {
                # PyInstaller one-file startup extracts to a temporary directory;
                # retry briefly until the loopback server is listening.
            }
            Start-Sleep -Milliseconds 250
        }
        if (-not $Ready) {
            throw "Packaged Web UI did not return HTML within 10 seconds."
        }
    }
    finally {
        $WebProcess.Refresh()
        if (-not $WebProcess.HasExited) {
            Stop-Process -Id $WebProcess.Id -Force
            Wait-Process -Id $WebProcess.Id -ErrorAction SilentlyContinue
        }

        $SpawnedExecutableProcessIds = @(
            Get-CimInstance Win32_Process |
                Where-Object {
                    $_.ExecutablePath -eq $Executable -and
                    $_.ProcessId -notin $ExistingExecutableProcessIds
                } |
                ForEach-Object { $_.ProcessId }
        )
        foreach ($ProcessId in $SpawnedExecutableProcessIds) {
            Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
            Wait-Process -Id $ProcessId -ErrorAction SilentlyContinue
        }
    }
}

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$Spec = Join-Path $RepoRoot "packaging\x-cli.spec"
$Exe = Join-Path $RepoRoot "dist\x-windows-x86_64.exe"
$HashFile = Join-Path $RepoRoot "dist\x-windows-x86_64.exe.sha256"
$PreviousPythonUtf8 = $env:PYTHONUTF8
$PreviousPythonIoEncoding = $env:PYTHONIOENCODING

if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Missing project Python: $Python. Create .venv and install .[dev,release]."
}

Push-Location $RepoRoot
try {
    # GitHub's English Windows runners may default Python subprocesses to a
    # legacy code page such as cp1252. x-cli intentionally prints Chinese and
    # emoji, so every test, build, and smoke-test child must use UTF-8.
    $env:PYTHONUTF8 = "1"
    $env:PYTHONIOENCODING = "utf-8"

    $Version = (& $Python -c "from core.version import __version__; print(__version__)").Trim()
    if ($LASTEXITCODE -ne 0 -or -not $Version) {
        throw "Unable to read the release version from core.version."
    }

    & $Python -c "import build, PyInstaller" | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Missing release dependencies. Install with: pip install -e '.[dev,release]'"
    }

    if (-not $SkipTests) {
        $PytestTemp = Join-Path $RepoRoot ".pytest-tmp"
        New-Item -ItemType Directory -Path $PytestTemp -Force | Out-Null
        $env:TMP = $PytestTemp
        $env:TEMP = $PytestTemp
        & $Python -m pytest
        if ($LASTEXITCODE -ne 0) {
            throw "Test suite failed; release build stopped."
        }
    }

    & $Python -m build --no-isolation
    if ($LASTEXITCODE -ne 0) {
        throw "Python package build failed."
    }

    & $Python -m PyInstaller --noconfirm --clean $Spec
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $Exe -PathType Leaf)) {
        throw "PyInstaller did not produce $Exe."
    }

    $VersionResult = Invoke-CapturedUtf8Process `
        -Executable $Exe `
        -ProcessArguments @("--version")
    $VersionOutput = $VersionResult.Stdout.Trim()
    if ($VersionResult.ExitCode -ne 0 -or $VersionOutput -ne "x $Version") {
        throw "EXE version smoke test failed: expected 'x $Version', got '$VersionOutput'; stderr: $($VersionResult.Stderr)"
    }

    $NoteResult = Invoke-CapturedUtf8Process `
        -Executable $Exe `
        -ProcessArguments @("note", "--help")
    if ($NoteResult.ExitCode -ne 0 -or $NoteResult.Stdout -notmatch "usage: x note") {
        throw "EXE note help smoke test failed; stdout: $($NoteResult.Stdout); stderr: $($NoteResult.Stderr)"
    }

    Test-PackagedWebUi -Executable $Exe -RepositoryRoot $RepoRoot

    $Hash = (Get-FileHash -LiteralPath $Exe -Algorithm SHA256).Hash.ToUpperInvariant()
    "$Hash  x-windows-x86_64.exe" | Set-Content -LiteralPath $HashFile -Encoding ascii

    Write-Output "Built x-cli $Version"
    Write-Output "EXE: $Exe"
    Write-Output "SHA256: $Hash"
}
finally {
    Pop-Location
    if ($null -eq $PreviousPythonUtf8) {
        Remove-Item Env:PYTHONUTF8 -ErrorAction SilentlyContinue
    }
    else {
        $env:PYTHONUTF8 = $PreviousPythonUtf8
    }
    if ($null -eq $PreviousPythonIoEncoding) {
        Remove-Item Env:PYTHONIOENCODING -ErrorAction SilentlyContinue
    }
    else {
        $env:PYTHONIOENCODING = $PreviousPythonIoEncoding
    }
}
