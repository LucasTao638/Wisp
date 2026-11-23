# Wisp installer for Windows 10/11.
#
# One-line install (PowerShell):
#   irm https://raw.githubusercontent.com/YOUR-GITHUB-USERNAME/wisp/main/install.ps1 | iex
#
# Or, from an unzipped download: double-click setup.bat (which runs this with -Local).
#
# What it does: installs Python 3.13 (if needed), Wisp's Python packages, uv + Windows-MCP (app control),
# Claude Code (Wisp's brain), then adds Start Menu / desktop shortcuts and starts Wisp.

param([switch]$Local)

$ErrorActionPreference = "Stop"
$Repo = "YOUR-GITHUB-USERNAME/wisp"
$InstallDir = Join-Path $env:LOCALAPPDATA "Wisp"

function Say($text, $colour = "Cyan") { Write-Host $text -ForegroundColor $colour }
# Run an outside program (pip, uv, winget...). Many of them print progress on the error channel, which
# Windows PowerShell would otherwise treat as a failure. Judge them by their exit code instead.
function Run-Tool([string]$What, [scriptblock]$Command, [switch]$Quiet, [switch]$AllowFail) {
    $old = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $code = 1
    try {
        if ($Quiet) { & $Command 2>&1 | Out-Null } else { & $Command 2>&1 | ForEach-Object { Write-Host "$_" } }
        $code = $LASTEXITCODE
    } catch {
        Write-Host "$_"
    } finally {
        $ErrorActionPreference = $old
    }
    if ($code -ne 0 -and -not $AllowFail) { throw "$What failed (exit code $code). See the messages above." }
    return ($code -eq 0)
}

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
    $asset = $release.assets | Where-Object { $_.name -like "*windows*.zip" } | Select-Object -First 1
    if (-not $asset) { $asset = $release.assets | Where-Object { $_.name -like "*.zip" -and $_.name -notlike "*mac*" } | Select-Object -First 1 }
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
        Run-Tool "Updating Wisp" { py -V:3.13 (Join-Path $InstallDir "updater.py") $zip } | Out-Null
    } else {
        New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
        Copy-Item (Join-Path $source.FullName "*") $InstallDir -Recurse -Force
    }
    Say "Installed to $InstallDir" "Green"
}

# ---------- 2. Python 3.13 ----------
Say "[2/5] Checking Python 3.13..."
Refresh-Path
$hasPy = (Get-Command py -ErrorAction SilentlyContinue) -and (Run-Tool "Python check" { py -V:3.13 --version } -Quiet -AllowFail)
if (-not $hasPy) {
    Say "Installing Python 3.13 (this can take a minute)..."
    Run-Tool "Installing Python" { winget install -e --id Python.Python.3.13 --scope user --silent --accept-package-agreements --accept-source-agreements } -AllowFail | Out-Null
    Refresh-Path
    if (-not (Run-Tool "Python check" { py -V:3.13 --version } -Quiet -AllowFail)) {
        throw "Python 3.13 didn't install. Install it from python.org, then run this again."
    }
}

# ---------- 3. Python packages ----------
Say "[3/5] Installing Wisp's packages (voice, hotkeys, tray)..."
Run-Tool "Updating pip" { py -V:3.13 -m pip install --upgrade --quiet --disable-pip-version-check pip } -AllowFail | Out-Null
Run-Tool "Installing Wisp's packages" { py -V:3.13 -m pip install --quiet --disable-pip-version-check -r (Join-Path $InstallDir "requirements.txt") } | Out-Null

# ---------- 4. uv + Windows-MCP (app control) ----------
Say "[4/5] Installing app control (Windows-MCP)..."
Refresh-Path
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    Refresh-Path
}
Run-Tool "Installing Windows-MCP (app control)" { uv tool install windows-mcp --python 3.13 --force } -Quiet | Out-Null

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
