$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = (Get-Command python -ErrorAction Stop).Source
}

& $python -m PyInstaller --clean --noconfirm "Muzo Player.spec"
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE."
}

$executable = Join-Path $projectRoot "dist\Muzo Player.exe"
if (-not (Test-Path $executable)) {
    throw "Build completed without creating the expected executable: $executable"
}

Write-Output "Portable executable created: $executable"
