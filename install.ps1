# Wisp installer for Windows 10/11.
#
# One-line install (PowerShell):
#   irm https://raw.githubusercontent.com/LucasTao638/Wisp/main/install.ps1 | iex
#
# Or, from an unzipped download: double-click setup.bat (which runs this with -Local).
#
# What it does: installs Python 3.13 (if needed), Wisp's Python packages, uv + Windows-MCP (app control),
# Claude Code (Wisp's brain), then adds Start Menu / desktop shortcuts and starts Wisp.

param([switch]$Local)

$ErrorActionPreference = "Stop"
$Repo = "LucasTao638/Wisp"
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
    try {
        $release = Invoke-RestMethod "https://api.github.com/repos/$Repo/releases/latest" -Headers @{ "User-Agent" = "Wisp-installer" }
    } catch {
        throw "Couldn't find a published Wisp release at github.com/$Repo/releases (the repo may be private, or no release is published yet). Details: $($_.Exception.Message)"
    }
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
$mcpOk = Run-Tool "Installing Windows-MCP (app control)" { uv tool install windows-mcp --python 3.13 --force } -AllowFail
if (-not $mcpOk) {
    # Most common cause: Wisp is still running, so Windows-MCP's files are in use and can't be replaced.
    Say "Windows-MCP didn't install (see the message above). Closing Wisp and trying once more..." "Yellow"
    Get-Process windows-mcp -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Get-CimInstance Win32_Process -Filter "Name = 'pythonw.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like "*app.py*" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 2
    $mcpOk = Run-Tool "Installing Windows-MCP (app control)" { uv tool install windows-mcp --python 3.13 --force } -AllowFail
}
if ($mcpOk) {
    Say "App control is installed." "Green"
} else {
    Say "App control (Windows-MCP) still didn't install. Wisp will still work, and will try to start it another way." "Yellow"
    Say "Please send the message above to the developer (Wisp menu > Send feedback)." "Yellow"
}

# ---------- 5. Claude Code ----------
Say "[5/5] Installing Claude Code (Wisp's brain)..."
Refresh-Path
$claudeExe = "$env:USERPROFILE\.local\bin\claude.exe"
if (-not (Get-Command claude -ErrorAction SilentlyContinue) -and -not (Test-Path $claudeExe)) {
    try {
        $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
        Invoke-RestMethod https://claude.ai/install.ps1 | Invoke-Expression
    } catch {
        Write-Host "$_"
    } finally { $ErrorActionPreference = $old }
    Refresh-Path
}
# make sure ~/.local/bin (Claude Code, uv) stays on PATH for next time
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
$localBin = "$env:USERPROFILE\.local\bin"
if ($userPath -notlike "*$localBin*") { [Environment]::SetEnvironmentVariable("Path", "$userPath;$localBin", "User") }
if ((Get-Command claude -ErrorAction SilentlyContinue) -or (Test-Path $claudeExe)) {
    Say "Claude Code is installed." "Green"
} else {
    Say "Claude Code didn't install here - no problem, Wisp's setup screen has an 'Install it for me' button." "Yellow"
}

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

Say "`nDone! Starting Wisp - its setup screen connects Claude (no more typing commands).`n" "Green"
Start-Process $pyw -ArgumentList "`"$(Join-Path $InstallDir 'app.py')`"" -WorkingDirectory $InstallDir
