param(
    [string]$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..\.."))
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path $RepositoryRoot).Path
$toolRoot = Join-Path $root ".tools\content-quality"
$downloadRoot = Join-Path $toolRoot "downloads"
New-Item -ItemType Directory -Force -Path $downloadRoot | Out-Null

function Install-ZipTool {
    param(
        [string]$Name,
        [string]$Version,
        [string]$Url,
        [string]$ExpectedSha256,
        [string]$ExecutableRelativePath
    )

    $installRoot = Join-Path $toolRoot "$Name\$Version"
    $executable = Join-Path $installRoot $ExecutableRelativePath
    if (Test-Path -LiteralPath $executable) {
        return $executable
    }

    $archive = Join-Path $downloadRoot "$Name-$Version.zip"
    curl.exe -L --fail --silent --show-error $Url --output $archive
    if ($LASTEXITCODE -ne 0) {
        throw "download failed: $Url"
    }
    $actualSha256 = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualSha256 -ne $ExpectedSha256.ToLowerInvariant()) {
        throw "$Name checksum mismatch: expected $ExpectedSha256, got $actualSha256"
    }

    New-Item -ItemType Directory -Force -Path $installRoot | Out-Null
    Expand-Archive -LiteralPath $archive -DestinationPath $installRoot -Force
    if (-not (Test-Path -LiteralPath $executable)) {
        throw "$Name executable not found after extraction: $executable"
    }
    return $executable
}

function Install-PythonWheelTool {
    param(
        [string]$Name,
        [string]$Version,
        [string]$Url,
        [string]$ExpectedSha256,
        [string]$ExecutableRelativePath
    )

    $installRoot = Join-Path $toolRoot "$Name\$Version"
    $executable = Join-Path $installRoot $ExecutableRelativePath
    if (Test-Path -LiteralPath $executable) {
        return $executable
    }

    $wheel = Join-Path $downloadRoot "$Name-$Version-py3-none-any.whl"
    curl.exe -L --fail --silent --show-error $Url --output $wheel
    if ($LASTEXITCODE -ne 0) {
        throw "download failed: $Url"
    }
    $actualSha256 = (Get-FileHash -LiteralPath $wheel -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualSha256 -ne $ExpectedSha256.ToLowerInvariant()) {
        throw "$Name checksum mismatch: expected $ExpectedSha256, got $actualSha256"
    }

    New-Item -ItemType Directory -Force -Path $installRoot | Out-Null
    & (Get-Command py.exe).Source -3.13 -m pip install `
        --disable-pip-version-check --no-deps --target $installRoot $wheel
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $executable)) {
        throw "$Name installation failed: $executable"
    }
    return $executable
}

$vale = Install-ZipTool `
    -Name "vale" `
    -Version "3.15.1" `
    -Url "https://github.com/vale-cli/vale/releases/download/v3.15.1/vale_3.15.1_Windows_64-bit.zip" `
    -ExpectedSha256 "3395fca0ddfb10a9b6caa28e091d5df709b1d6b6579afb7dece852cad89b94f3" `
    -ExecutableRelativePath "vale.exe"

$lychee = Install-ZipTool `
    -Name "lychee" `
    -Version "0.24.2" `
    -Url "https://github.com/lycheeverse/lychee/releases/download/lychee-v0.24.2/lychee-x86_64-pc-windows-msvc.zip" `
    -ExpectedSha256 "32975d1493ee1a975d6bb41e4fb56fe419cb442ded628bb772ba2e614acfacad" `
    -ExecutableRelativePath "lychee-x86_64-pc-windows-msvc\lychee.exe"

$gitleaks = Install-ZipTool `
    -Name "gitleaks" `
    -Version "8.30.1" `
    -Url "https://github.com/gitleaks/gitleaks/releases/download/v8.30.1/gitleaks_8.30.1_windows_x64.zip" `
    -ExpectedSha256 "d29144deff3a68aa93ced33dddf84b7fdc26070add4aa0f4513094c8332afc4e" `
    -ExecutableRelativePath "gitleaks.exe"

$codespell = Install-PythonWheelTool `
    -Name "codespell" `
    -Version "2.4.2" `
    -Url "https://files.pythonhosted.org/packages/42/a1/52fa05533e95fe45bcc09bcf8a503874b1c08f221a4e35608017e0938f55/codespell-2.4.2-py3-none-any.whl" `
    -ExpectedSha256 "97e0c1060cf46bd1d5db89a936c98db8c2b804e1fdd4b5c645e82a1ec6b1f886" `
    -ExecutableRelativePath "bin\codespell.exe"

Write-Output "vale=$vale"
Write-Output "lychee=$lychee"
Write-Output "gitleaks=$gitleaks"
Write-Output "codespell=$codespell"
Write-Output "markdownlint_cli2=0.23.0 (pinned through npx)"
Write-Output "zhlint=0.8.2 (pinned through npx)"
Write-Output "jscpd=5.0.12 (pinned through npx)"
Write-Output "mermaid_cli=11.16.0 (pinned through npx; on-demand validation)"
