# Music Pipeline build/deploy entry point (Windows / PowerShell).
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File tools\build.ps1 <target>
#
# Targets:
#   web        build the Docker images and start the web app (API + UI) with Docker Compose
#   web-build  build the Docker images and package them as dist\docker.tar.gz (plus a compose file)
#   desktop    build the desktop app with PyInstaller into a single file, dist\MusicPipeline.exe
param(
    [Parameter(Position = 0)]
    [ValidateSet("web", "web-build", "desktop")]
    [string]$Target
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not $Target) {
    Get-Content $PSCommandPath -TotalCount 9 | ForEach-Object { $_ -replace "^# ?", "" }
    exit 1
}

function Invoke-Checked {
    & $args[0] $args[1..($args.Length - 1)]
    if ($LASTEXITCODE -ne 0) { throw "Command failed ($LASTEXITCODE): $($args -join ' ')" }
}

function Assert-Docker {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw "Docker is not installed or not on PATH." }
    docker compose version *> $null
    if ($LASTEXITCODE -ne 0) { throw "Docker Compose v2 is required (docker compose)." }
    docker info *> $null
    if ($LASTEXITCODE -ne 0) { throw "The Docker daemon is not running. Start Docker Desktop and retry." }
}

# Compose bind-mounts cookies.txt; a missing file would be created as a directory.
function Initialize-RuntimeFiles {
    New-Item -ItemType Directory -Force downloads, logs | Out-Null
    if (-not (Test-Path cookies.txt)) { New-Item -ItemType File cookies.txt | Out-Null }
}

function Build-Web {
    Assert-Docker
    Initialize-RuntimeFiles
    Invoke-Checked docker compose up -d --build
    Write-Host ""
    Write-Host "Music Pipeline web is running."
    Write-Host "  UI:  http://localhost:3000"
    Write-Host "  API: http://localhost:8000"
    Write-Host "Stop with: docker compose down"
}

# docker save output is binary, so compress it with .NET instead of the PowerShell pipeline.
function Compress-File($source, $destination) {
    $in = [IO.File]::OpenRead($source)
    try {
        $out = [IO.File]::Create($destination)
        try {
            $gzip = New-Object IO.Compression.GZipStream($out, [IO.Compression.CompressionMode]::Compress)
            try { $in.CopyTo($gzip) } finally { $gzip.Dispose() }
        } finally { $out.Dispose() }
    } finally { $in.Dispose() }
}

function Build-WebPackage {
    Assert-Docker
    Invoke-Checked docker compose build
    New-Item -ItemType Directory -Force dist | Out-Null
    foreach ($name in "docker.tar.gz", "docker.tar", "docker-compose.yml", "cookies.txt") {
        Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path "dist" $name)
    }
    Invoke-Checked docker save -o dist\docker.tar music-pipeline-api:latest music-pipeline-web:latest
    Compress-File (Join-Path $Root "dist\docker.tar") (Join-Path $Root "dist\docker.tar.gz")
    Remove-Item dist\docker.tar

    # The packaged compose file uses the loaded images, so drop the build sections.
    $compose = (Get-Content docker-compose.yml -Raw) -replace "(?m)^    build:\r?\n(      .*\r?\n)+", ""
    Set-Content -Path dist\docker-compose.yml -Value $compose -NoNewline -Encoding utf8
    New-Item -ItemType File dist\cookies.txt | Out-Null

    Write-Host ""
    Write-Host "Docker package ready in dist\:"
    Write-Host "  docker.tar.gz, docker-compose.yml, cookies.txt"
    Write-Host "On the target machine: docker load -i docker.tar.gz; docker compose up -d"
}

function Build-Desktop {
    $venvPython = Join-Path $Root ".venv\Scripts\python.exe"
    if (-not (Test-Path $venvPython)) { Invoke-Checked powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Root "tools\setup.ps1") }
    Invoke-Checked $venvPython -m PyInstaller --clean --noconfirm apps\desktop\music_pipeline_desktop.spec
    Write-Host ""
    Write-Host "Desktop build finished."
    Write-Host "Output: dist\MusicPipeline.exe"
}

switch ($Target) {
    "web" { Build-Web }
    "web-build" { Build-WebPackage }
    "desktop" { Build-Desktop }
}
