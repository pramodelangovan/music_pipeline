# Installs Deno and ffmpeg on Windows. Run from PowerShell:
#   powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
$ErrorActionPreference = "Stop"

function Test-Cmd($name) { [bool](Get-Command $name -ErrorAction SilentlyContinue) }

function Install-WithWinget($id) {
    winget install --id $id -e --silent --accept-package-agreements --accept-source-agreements
}

if (Test-Cmd ffmpeg) {
    Write-Host "ffmpeg already installed"
} else {
    Write-Host "Installing ffmpeg..."
    if (Test-Cmd winget) { Install-WithWinget "Gyan.FFmpeg" }
    elseif (Test-Cmd choco) { choco install ffmpeg -y }
    elseif (Test-Cmd scoop) { scoop install ffmpeg }
    else { throw "No package manager (winget/choco/scoop) found; install ffmpeg manually." }
}

if (Test-Cmd deno) {
    Write-Host "deno already installed"
} else {
    Write-Host "Installing Deno..."
    if (Test-Cmd winget) { Install-WithWinget "DenoLand.Deno" }
    else { irm https://deno.land/install.ps1 | iex }
}

# Refresh PATH for the current session
$env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
            [Environment]::GetEnvironmentVariable("Path", "User") + ";" +
            "$env:USERPROFILE\.deno\bin"

Write-Host ""
if (Test-Cmd ffmpeg) { ffmpeg -version | Select-Object -First 1 } else { Write-Warning "ffmpeg not on PATH yet; restart your terminal." }
if (Test-Cmd deno) { deno --version | Select-Object -First 1 } else { Write-Warning "deno not on PATH yet; restart your terminal." }
