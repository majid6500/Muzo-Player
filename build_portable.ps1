$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

$vlcVersion = (Get-Content -LiteralPath (Join-Path $projectRoot "vlc-runtime-version.txt") -Raw).Trim()
if ($vlcVersion -notmatch '^\d+\.\d+\.\d+$') {
    throw "vlc-runtime-version.txt must contain a VLC version such as 3.0.23."
}

$runtimeDirectory = Join-Path $projectRoot ".vlc-runtime\$vlcVersion"
$requiredRuntimeFiles = @(
    (Join-Path $runtimeDirectory "libvlc.dll"),
    (Join-Path $runtimeDirectory "libvlccore.dll"),
    (Join-Path $runtimeDirectory "plugins")
)
if (-not (($requiredRuntimeFiles | ForEach-Object { Test-Path -LiteralPath $_ }) -notcontains $false)) {
    $runtimeCache = Join-Path $projectRoot ".vlc-runtime"
    $archivePath = Join-Path $runtimeCache "vlc-$vlcVersion-win64.zip"
    $extractDirectory = Join-Path $runtimeCache "extract-$vlcVersion"
    $downloadUrl = "https://get.videolan.org/vlc/$vlcVersion/win64/vlc-$vlcVersion-win64.zip"
    $runtimeSourceDirectory = $null

    $installedVlcCandidates = @()
    if ($env:VLC_HOME) {
        $installedVlcCandidates += $env:VLC_HOME
    }
    if ($env:ProgramFiles) {
        $installedVlcCandidates += (Join-Path $env:ProgramFiles "VideoLAN\VLC")
    }
    if (${env:ProgramFiles(x86)}) {
        $installedVlcCandidates += (Join-Path ${env:ProgramFiles(x86)} "VideoLAN\VLC")
    }
    foreach ($candidate in $installedVlcCandidates) {
        $candidateLibrary = Join-Path $candidate "libvlc.dll"
        if (-not (Test-Path -LiteralPath $candidateLibrary)) {
            continue
        }
        $peBytes = [System.IO.File]::ReadAllBytes($candidateLibrary)
        if ($peBytes.Length -lt 0x40) {
            continue
        }
        $peOffset = [System.BitConverter]::ToInt32($peBytes, 0x3c)
        if ($peOffset -lt 0 -or $peOffset + 6 -gt $peBytes.Length) {
            continue
        }
        $machine = [System.BitConverter]::ToUInt16($peBytes, $peOffset + 4)
        if ($machine -eq 0x8664 -and
            (Test-Path -LiteralPath (Join-Path $candidate "libvlccore.dll")) -and
            (Test-Path -LiteralPath (Join-Path $candidate "plugins")) -and
            (Get-Item -LiteralPath $candidateLibrary).VersionInfo.FileVersion -eq $vlcVersion) {
            $runtimeSourceDirectory = $candidate
            break
        }
    }

    New-Item -ItemType Directory -Path $runtimeCache -Force | Out-Null
    if (-not $runtimeSourceDirectory) {
        $archiveIsAvailable = (Test-Path -LiteralPath $archivePath) -and
            ((Get-Item -LiteralPath $archivePath).Length -ge 10MB)
        if (-not $archiveIsAvailable) {
            if (Test-Path -LiteralPath $archivePath) {
                Remove-Item -LiteralPath $archivePath -Force
            }
            Write-Output "Downloading official 64-bit VLC $vlcVersion runtime..."
            & curl.exe --fail --location --retry 3 --retry-delay 2 --output $archivePath $downloadUrl
            if ($LASTEXITCODE -ne 0) {
                throw "Could not download the official VLC runtime (curl exit code $LASTEXITCODE)."
            }
            if ((Get-Item -LiteralPath $archivePath).Length -lt 10MB) {
                throw "The downloaded VLC archive is unexpectedly small and is not trusted."
            }
        }

        if (Test-Path -LiteralPath $extractDirectory) {
            Remove-Item -LiteralPath $extractDirectory -Recurse -Force
        }
        Expand-Archive -LiteralPath $archivePath -DestinationPath $extractDirectory

        $library = Get-ChildItem -LiteralPath $extractDirectory -Recurse -File -Filter "libvlc.dll" |
            Where-Object {
                (Test-Path -LiteralPath (Join-Path $_.DirectoryName "libvlccore.dll")) -and
                (Test-Path -LiteralPath (Join-Path $_.DirectoryName "plugins"))
            } |
            Select-Object -First 1
        if (-not $library) {
            throw "The official VLC archive did not contain libvlc.dll, libvlccore.dll, and plugins."
        }
        $runtimeSourceDirectory = $library.DirectoryName
    }

    if (Test-Path -LiteralPath $runtimeDirectory) {
        Remove-Item -LiteralPath $runtimeDirectory -Recurse -Force
    }
    New-Item -ItemType Directory -Path $runtimeDirectory -Force | Out-Null
    Copy-Item -Path (Join-Path $runtimeSourceDirectory "*") -Destination $runtimeDirectory -Recurse -Force
    if (Test-Path -LiteralPath $extractDirectory) {
        Remove-Item -LiteralPath $extractDirectory -Recurse -Force
    }

    foreach ($path in $requiredRuntimeFiles) {
        if (-not (Test-Path -LiteralPath $path)) {
            throw "The VLC runtime is incomplete after extraction: $path"
        }
    }
}

$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = (Get-Command python -ErrorAction Stop).Source
}

$pythonArchitecture = & $python -c "import struct; print(struct.calcsize('P') * 8)"
if ($LASTEXITCODE -ne 0 -or $pythonArchitecture.Trim() -ne "64") {
    throw "The portable VLC runtime is 64-bit; build Muzo Player with 64-bit Python."
}

& $python -m PyInstaller --clean --noconfirm "Muzo Player.spec"
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE."
}

$executable = Join-Path $projectRoot "dist\Muzo Player.exe"
if (-not (Test-Path $executable)) {
    throw "Build completed without creating the expected executable: $executable"
}

Write-Output "Bundled VLC runtime: $runtimeDirectory"
Write-Output "Portable executable created: $executable"
