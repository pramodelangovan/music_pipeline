# Sets up Music Pipeline on Windows:
#   1. system packages: Python, ffmpeg, Deno
#   2. a .venv in the project root (created only if missing)
#   3. every Python requirement (requirements-desktop.txt, which includes requirements.txt)
#
# Usage (PowerShell):
#   powershell -ExecutionPolicy Bypass -File tools\setup.ps1
#   -DepsOnly   only ffmpeg and Deno (used by the app itself when it finds them missing)
param([switch]$DepsOnly)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

function Test-Cmd($name) { [bool](Get-Command $name -ErrorAction SilentlyContinue) }

function Update-SessionPath {
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [Environment]::GetEnvironmentVariable("Path", "User") + ";" +
                "$env:USERPROFILE\.deno\bin"
}

function Install-WithWinget($id) {
    winget install --id $id -e --silent --accept-package-agreements --accept-source-agreements
}

# The Microsoft Store "python" alias exists on PATH but cannot run, so execute it to be sure.
function Get-Python {
    foreach ($candidate in @("py", "python")) {
        if (Test-Cmd $candidate) {
            & $candidate --version *> $null
            if ($LASTEXITCODE -eq 0) { return $candidate }
        }
    }
    return $null
}

function Invoke-Checked {
    & $args[0] $args[1..($args.Length - 1)]
    if ($LASTEXITCODE -ne 0) { throw "Command failed ($LASTEXITCODE): $($args -join ' ')" }
}

function Install-Python {
    if (Get-Python) { Write-Host "python already installed"; return }
    Write-Host "Installing Python..."
    if (Test-Cmd winget) { Install-WithWinget "Python.Python.3.12" }
    else { throw "winget not found; install Python 3.10+ manually from python.org." }
    Update-SessionPath
    if (-not (Get-Python)) { throw "Python was installed but is not on PATH yet; restart your terminal and re-run setup." }
}

function Install-Ffmpeg {
    if (Test-Cmd ffmpeg) { Write-Host "ffmpeg already installed"; return }
    Write-Host "Installing ffmpeg..."
    if (Test-Cmd winget) { Install-WithWinget "Gyan.FFmpeg" }
    elseif (Test-Cmd choco) { choco install ffmpeg -y }
    elseif (Test-Cmd scoop) { scoop install ffmpeg }
    else { throw "No package manager (winget/choco/scoop) found; install ffmpeg manually." }
}

function Install-Deno {
    if (Test-Cmd deno) { Write-Host "deno already installed"; return }
    Write-Host "Installing Deno..."
    if (Test-Cmd winget) { Install-WithWinget "DenoLand.Deno" }
    else { irm https://deno.land/install.ps1 | iex }
}

function Initialize-Venv {
    $venvPython = Join-Path $Root ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        Write-Host ".venv already exists"
    } else {
        Write-Host "Creating .venv..."
        $py = Get-Python
        Invoke-Checked $py -m venv (Join-Path $Root ".venv")
    }
    Write-Host "Installing Python requirements..."
    Invoke-Checked $venvPython -m pip install --upgrade pip
    Invoke-Checked $venvPython -m pip install -r (Join-Path $Root "requirements-desktop.txt")
}

if (-not $DepsOnly) { Install-Python }
Install-Ffmpeg
Install-Deno
Update-SessionPath
if (-not $DepsOnly) { Initialize-Venv }

Write-Host ""
if (Test-Cmd ffmpeg) { ffmpeg -version | Select-Object -First 1 } else { Write-Warning "ffmpeg not on PATH yet; restart your terminal." }
if (Test-Cmd deno) { deno --version | Select-Object -First 1 } else { Write-Warning "deno not on PATH yet; restart your terminal." }
if (-not $DepsOnly) {
    Write-Host ""
    Write-Host "Setup complete. Activate the environment with: .venv\Scripts\Activate.ps1"
}
