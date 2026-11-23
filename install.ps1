# Wisp installer for Windows 10/11.
#
# One-line install (PowerShell):
#   irm https://raw.githubusercontent.com/LucasTao638/wisp/main/install.ps1 | iex
#
# Or, from an unzipped download: double-click setup.bat (which runs this with -Local).
#
# What it does: installs Python 3.13 (if needed), Wisp's Python packages, uv + Windows-MCP (app control),
# Claude Code (Wisp's brain), then adds Start Menu / desktop shortcuts and starts Wisp.

param([switch]$Local)

$ErrorActionPreference = "Stop"
$Repo = "LucasTao638/wisp"
$InstallDir = Join-Path $env:LOCALAPPDATA "Wisp"

function Say($text, $colour = "Cyan") { Write-Host $text -ForegroundColor $colour }
function Refresh-Path {
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "User") + ";" + [Environment]::GetEnvironmentVariable("Path", "Machine")
    $extra = @("$env:USERPROFILE\.local\bin", "$env:LOCALAPPDATA\Python\bin", "$env:LOCALAPPDATA\Programs\Python\Launcher")
    foreach ($p in $extra) { if ((Test-Path $p) -and ($env:Path -notlike "*$p*")) { $env:Path += ";$p" } }
}

Say "`n=== Installing Wisp ===`n"

# ---------- 1. Get the files ----------
if ($Local) {
    $InstallDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    Say "Using the files in $InstallDir"
} else {
    Say "[1/5] Downloading the latest Wisp..."
    $release = Invoke-RestMethod "https://api.github.com/repos/$Repo/releases/latest" -Headers @{ "User-Agent" = "Wisp-installer" }
    $asset = $release.assets | Where-Object { $_.name -like "*.zip" } | Select-Object -First 1
    if (-not $asset) { throw "The latest release has no zip attached." }
    $zip = Join-Path $env:TEMP $asset.name
    Invoke-WebRequest $asset.browser_download_url -OutFile $zip -UseBasicParsing
    $unpacked = Join-Path $env:TEMP "wisp-install"
    if (Test-Path $unpacked) { Remove-Item $unpacked -Recurse -Force }
    Expand-Archive $zip $unpacked -Force
    $source = Get-ChildItem $unpacked -Directory | Select-Object -First 1
    if (-not (Test-Path (Join-Path $source.FullName "core.py"))) { $source = Get-Item $unpacked }
    if (Test-Path (Join-Path $InstallDir "core.py")) {
        Say "Wisp is already installed - updating it (your settings and memory are kept)."
        & py -V:3.13 (Join-Path $InstallDir "updater.py") $zip
    } else {
        New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
        Copy-Item (Join-Path $source.FullName "*") $InstallDir -Recurse -Force
    }
    Say "Installed to $InstallDir" "Green"
}

# ---------- 2. Python 3.13 ----------
Say "[2/5] Checking Python 3.13..."
Refresh-Path
$hasPy = $false
try { & py -V:3.13 --version 2>$null | Out-Null; if ($LASTEXITCODE -eq 0) { $hasPy = $true } } catch {}
if (-not $hasPy) {
    Say "Installing Python 3.13 (this can take a minute)..."
    winget install -e --id Python.Python.3.13 --scope user --silent --accept-package-agreements --accept-source-agreements
    Refresh-Path
    & py -V:3.13 --version
    if ($LASTEXITCODE -ne 0) { throw "Python 3.13 didn't install. Install it from python.org, then run this again." }
}

# ---------- 3. Python packages ----------
Say "[3/5] Installing Wisp's packages (voice, hotkeys, tray)..."
& py -V:3.13 -m pip install --upgrade --quiet pip
& py -V:3.13 -m pip install --quiet -r (Join-Path $InstallDir "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "Package install failed. See the messages above." }

# ---------- 4. uv + Windows-MCP (app control) ----------
Say "[4/5] Installing app control (Windows-MCP)..."
Refresh-Path
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    Refresh-Path
}
& uv tool install windows-mcp --python 3.13 --force 2>$null | Out-Null

# ---------- 5. Claude Code ----------
Say "[5/5] Installing Claude Code (Wisp's brain)..."
Refresh-Path
if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
    Invoke-RestMethod https://claude.ai/install.ps1 | Invoke-Expression
    Refresh-Path
}
# make sure ~/.local/bin (Claude Code, uv) stays on PATH for next time
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
$localBin = "$env:USERPROFILE\.local\bin"
if ($userPath -notlike "*$localBin*") { [Environment]::SetEnvironmentVariable("Path", "$userPath;$localBin", "User") }

# ---------- shortcuts ----------
$pyw = (& py -V:3.13 -c "import sys, os; print(os.path.join(os.path.dirname(sys.executable), 'pythonw.exe'))").Trim()
$shell = New-Object -ComObject WScript.Shell
$places = @([Environment]::GetFolderPath("Programs"), [Environment]::GetFolderPath("Desktop"))
foreach ($folder in $places) {
    $lnk = $shell.CreateShortcut((Join-Path $folder "Wisp.lnk"))
    $lnk.TargetPath = $pyw
    $lnk.Arguments = "`"$(Join-Path $InstallDir 'app.py')`""
    $lnk.WorkingDirectory = $InstallDir
    $lnk.Description = "Wisp - voice assistant"
    $lnk.Save()
}

Say "`nDone! Starting Wisp - the setup screen will ask for your Anthropic API key.`n" "Green"
Start-Process $pyw -ArgumentList "`"$(Join-Path $InstallDir 'app.py')`"" -WorkingDirectory $InstallDir
