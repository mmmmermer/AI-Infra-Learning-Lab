[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..\..")).Path
$Version = "v0.32.0"
$ExpectedSha256 = "0bcb2d1cfedc1912d664014db716937e8a0e843e91c6807b4db2025dbc8989fa"
$InstallDirectory = Join-Path $RepositoryRoot ".tools\kind\$Version"
$KindPath = Join-Path $InstallDirectory "kind.exe"
$DownloadUrl = "https://github.com/kubernetes-sigs/kind/releases/download/$Version/kind-windows-amd64"

New-Item -ItemType Directory -Force $InstallDirectory | Out-Null
if (-not (Test-Path -LiteralPath $KindPath)) {
    Invoke-WebRequest -Uri $DownloadUrl -OutFile $KindPath
}

$actualSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $KindPath).Hash.ToLowerInvariant()
if ($actualSha256 -ne $ExpectedSha256) {
    throw "kind checksum mismatch: expected $ExpectedSha256, got $actualSha256"
}

$versionOutput = & $KindPath version
if ($LASTEXITCODE -ne 0 -or $versionOutput -notmatch [regex]::Escape($Version)) {
    throw "kind version verification failed: $versionOutput"
}

[pscustomobject]@{
    kind_path = $KindPath
    version = $Version
    sha256 = $actualSha256
    source = $DownloadUrl
} | Format-List
