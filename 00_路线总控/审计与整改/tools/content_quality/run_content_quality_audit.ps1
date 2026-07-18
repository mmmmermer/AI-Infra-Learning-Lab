param(
    [string]$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..\..")),
    [string]$OutputDirectory = ""
)

$ErrorActionPreference = "Stop"
$utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8
$env:PYTHONUTF8 = "1"
$root = (Resolve-Path $RepositoryRoot).Path
$auditRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$output = if ($OutputDirectory) {
    Join-Path $root $OutputDirectory
} else {
    Join-Path $auditRoot "artifacts\content_quality_audit_2026-07-11"
}
$sanitized = Join-Path $root ".tools\content-quality\zhlint-input"
$configRoot = $PSScriptRoot
New-Item -ItemType Directory -Force -Path $output | Out-Null
New-Item -ItemType Directory -Force -Path $sanitized | Out-Null

function Convert-RedirectedArtifactsToUtf8 {
    param([Parameter(Mandatory = $true)][string]$Directory)

    Get-ChildItem -LiteralPath $Directory -File | Where-Object {
        $_.Extension -in @(".json", ".log")
    } | ForEach-Object {
        $bytes = [IO.File]::ReadAllBytes($_.FullName)
        $hasUtf16Bom = $bytes.Length -ge 2 -and (
            ($bytes[0] -eq 0xFF -and $bytes[1] -eq 0xFE) -or
            ($bytes[0] -eq 0xFE -and $bytes[1] -eq 0xFF)
        )
        if ($hasUtf16Bom) {
            $content = [IO.File]::ReadAllText($_.FullName)
            [IO.File]::WriteAllText($_.FullName, $content, $utf8)
        }
    }
}

function Convert-RepositoryPathsToPortable {
    param(
        [Parameter(Mandatory = $true)][string]$Directory,
        [Parameter(Mandatory = $true)][string]$RepositoryRoot
    )

    $escapedWindowsRoot = $RepositoryRoot.Replace("\", "\\")
    $forwardSlashRoot = $RepositoryRoot.Replace("\", "/")
    Get-ChildItem -LiteralPath $Directory -Recurse -File | Where-Object {
        $_.Extension -in @(".json", ".log", ".csv")
    } | ForEach-Object {
        $content = [IO.File]::ReadAllText($_.FullName)
        $portable = $content.Replace($escapedWindowsRoot, "<repository>")
        $portable = $portable.Replace($RepositoryRoot, "<repository>")
        $portable = $portable.Replace($forwardSlashRoot, "<repository>")
        if ($portable -ne $content) {
            [IO.File]::WriteAllText($_.FullName, $portable, $utf8)
        }
    }
}

& (Join-Path $configRoot "install_open_source_checkers.ps1") -RepositoryRoot $root

$python = (Get-Command py.exe).Source
$npx = (Get-Command npx.cmd).Source
$vale = Join-Path $root ".tools\content-quality\vale\3.15.1\vale.exe"
$lychee = Join-Path $root ".tools\content-quality\lychee\0.24.2\lychee-x86_64-pc-windows-msvc\lychee.exe"
$gitleaks = Join-Path $root ".tools\content-quality\gitleaks\8.30.1\gitleaks.exe"
$codespellRoot = Join-Path $root ".tools\content-quality\codespell\2.4.2"
$codespell = Join-Path $codespellRoot "bin\codespell.exe"
$valeConfig = Join-Path $configRoot ".vale.ini"
$valeInputs = @(
    Get-ChildItem -LiteralPath $root -Directory |
        Where-Object { $_.Name -match "^[0-9]{2}_" } |
        ForEach-Object { $_.FullName }
    Get-ChildItem -LiteralPath $root -File -Filter "*.md" |
        ForEach-Object { $_.FullName }
)
$activeTextbooks = @(
    Get-ChildItem -LiteralPath (Join-Path $root "10_学习模块") -Recurse -File |
        Where-Object {
            ($_.Name.EndsWith("_适配教材.md") -or $_.Name.EndsWith("_章节教材.md")) -and
            $_.FullName -notmatch "[\\/]99_归档[\\/]"
        } |
        ForEach-Object { $_.FullName }
)
if ($activeTextbooks.Count -ne 22) {
    throw "expected 22 active textbook entry files, found $($activeTextbooks.Count)"
}
$m05ChapterFiles = @(
    Get-ChildItem -LiteralPath (Join-Path $root "10_学习模块\M05_任务队列与调度\教材章节") -File -Filter "*.md" |
        ForEach-Object { $_.FullName }
)
if ($m05ChapterFiles.Count -ne 13) {
    throw "expected 13 split M05 chapter files, found $($m05ChapterFiles.Count)"
}
$jscpdTextbookFiles = @($activeTextbooks) + @($m05ChapterFiles)

$ErrorActionPreference = "Continue"
Push-Location $root
try {
    & $python -3.13 (Join-Path $configRoot "prepare_zhlint_input.py") $root $sanitized |
        Out-File -LiteralPath (Join-Path $output "zhlint_prepare.log") -Encoding utf8

    & $npx --yes markdownlint-cli2@0.23.0 "**/*.md" `
        "#.tools/**" "#**/.venv/**" "#**/.pytest_cache/**" "#**/node_modules/**" `
        --config (Join-Path $configRoot "markdownlint.jsonc") `
        1> (Join-Path $output "markdownlint.stdout.log") `
        2> (Join-Path $output "markdownlint.stderr.log")
    $markdownlintExit = $LASTEXITCODE

    Push-Location $sanitized
    try {
        & $npx --yes zhlint@0.8.2 "**/*.md" `
            1> (Join-Path $output "zhlint.stdout.log") `
            2> (Join-Path $output "zhlint.stderr.log")
        $zhlintExit = $LASTEXITCODE
    } finally {
        Pop-Location
    }

    & $npx --yes jscpd@5.0.12 @jscpdTextbookFiles `
        --format markdown --min-lines 8 --min-tokens 80 `
        --reporters console --no-colors --no-tips `
        1> (Join-Path $output "jscpd.stdout.log") `
        2> (Join-Path $output "jscpd.stderr.log")
    $jscpdExit = $LASTEXITCODE

    & $vale --no-global "--config=$valeConfig" `
        --output=JSON @valeInputs `
        1> (Join-Path $output "vale.json") `
        2> (Join-Path $output "vale.stderr.log")
    $valeExit = $LASTEXITCODE

    $previousPythonPath = $env:PYTHONPATH
    $env:PYTHONPATH = $codespellRoot
    try {
        & $codespell @valeInputs `
            --skip "*.csv,*.json,*.lock,*.svg,*.log,*.toml,*.py,*.yaml,*.yml,*.ini,*.bak*,*/artifacts/*" `
            --ignore-words (Join-Path $configRoot "codespell_ignore_words.txt") `
            1> (Join-Path $output "codespell.stdout.log") `
            2> (Join-Path $output "codespell.stderr.log")
        $codespellExit = $LASTEXITCODE
    } finally {
        $env:PYTHONPATH = $previousPythonPath
    }

    & $lychee --format json --output (Join-Path $output "lychee.json") `
        --no-progress --exclude-all-private `
        --max-concurrency 8 --timeout 20 --max-retries 2 --retry-wait-time 2 `
        --exclude-path "(^|/)(\.tools|\.venv|node_modules)/" "**/*.md" `
        1> (Join-Path $output "lychee.stdout.log") `
        2> (Join-Path $output "lychee.stderr.log")
    $lycheeExit = $LASTEXITCODE

    & $lychee --format json --output (Join-Path $output "lychee_local.json") `
        --no-progress --offline `
        --exclude-path "(^|/)(\.tools|\.venv|node_modules|99_归档|artifacts)/" "**/*.md" `
        1> (Join-Path $output "lychee_local.stdout.log") `
        2> (Join-Path $output "lychee_local.stderr.log")
    $lycheeLocalExit = $LASTEXITCODE

    & $gitleaks git $root --enable-rule private-key --log-opts="--all" --max-archive-depth 2 `
        --no-banner --no-color --redact=100 `
        --report-format json --report-path (Join-Path $output "gitleaks_tracked_private_key.json") `
        1> (Join-Path $output "gitleaks.stdout.log") `
        2> (Join-Path $output "gitleaks.stderr.log")
    $gitleaksTrackedPrivateKeyExit = $LASTEXITCODE

    & $python -3.13 (Join-Path $configRoot "analyze_textbook_quality.py") $root $output `
        1> (Join-Path $output "custom_analysis.stdout.log") `
        2> (Join-Path $output "custom_analysis.stderr.log")
    $customExit = $LASTEXITCODE

    & $python -3.13 -m unittest discover -s $configRoot -p "test_*.py" `
        1> (Join-Path $output "content_quality_tests.stdout.log") `
        2> (Join-Path $output "content_quality_tests.stderr.log")
    $contentQualityTestsExit = $LASTEXITCODE

    & $python -3.13 (Join-Path $configRoot "analyze_pedagogy_quality.py") `
        $root (Join-Path $output "pedagogy_analysis.json") `
        1> (Join-Path $output "pedagogy_analysis.stdout.log") `
        2> (Join-Path $output "pedagogy_analysis.stderr.log")
    $pedagogyAnalysisExit = $LASTEXITCODE

    & $python -3.13 (Join-Path $configRoot "analyze_official_docs_structure.py") `
        $root `
        (Join-Path $output "pedagogy_analysis.json") `
        (Join-Path $output "official_docs_structure.json") `
        (Join-Path $output "official_docs_chapter_matrix.csv") `
        1> (Join-Path $output "official_docs_structure.stdout.log") `
        2> (Join-Path $output "official_docs_structure.stderr.log")
    $officialDocsStructureExit = $LASTEXITCODE

    Convert-RedirectedArtifactsToUtf8 -Directory $output
    Convert-RepositoryPathsToPortable -Directory $output -RepositoryRoot $root

    $blockerFailures = @()
    if ($gitleaksTrackedPrivateKeyExit -ne 0) {
        $blockerFailures += "gitleaks_tracked_private_key"
    }
    if ($customExit -ne 0) {
        $blockerFailures += "custom_analysis"
    }
    if ($contentQualityTestsExit -ne 0) {
        $blockerFailures += "content_quality_tests"
    }
    if ($pedagogyAnalysisExit -ne 0) {
        $blockerFailures += "pedagogy_analysis"
    }
    if ($officialDocsStructureExit -ne 0) {
        $blockerFailures += "official_docs_structure"
    }
    if ($lycheeLocalExit -ne 0) {
        $blockerFailures += "lychee_local_links"
    }
    $advisoryNonzero = @()
    foreach ($toolExit in ([ordered]@{
        markdownlint = $markdownlintExit
        zhlint = $zhlintExit
        jscpd = $jscpdExit
        vale = $valeExit
        codespell = $codespellExit
        lychee = $lycheeExit
    }).GetEnumerator()) {
        if ($toolExit.Value -ne 0) {
            $advisoryNonzero += $toolExit.Key
        }
    }

    $toolExitSummary = [ordered]@{
        audit_status = if ($blockerFailures.Count -eq 0) { "passed_with_advisories" } else { "failed" }
        active_textbook_count = $activeTextbooks.Count
        blocker_failures = $blockerFailures
        advisory_nonzero = $advisoryNonzero
        markdownlint_exit = $markdownlintExit
        zhlint_exit = $zhlintExit
        jscpd_exit = $jscpdExit
        vale_exit = $valeExit
        codespell_exit = $codespellExit
        lychee_exit = $lycheeExit
        lychee_local_exit = $lycheeLocalExit
        gitleaks_tracked_private_key_exit = $gitleaksTrackedPrivateKeyExit
        custom_analysis_exit = $customExit
        content_quality_tests_exit = $contentQualityTestsExit
        pedagogy_analysis_exit = $pedagogyAnalysisExit
        official_docs_structure_exit = $officialDocsStructureExit
    } | ConvertTo-Json
    [IO.File]::WriteAllText(
        (Join-Path $output "tool_exit_codes.json"),
        $toolExitSummary + [Environment]::NewLine,
        $utf8
    )
} finally {
    Pop-Location
}

$ErrorActionPreference = "Stop"
Write-Output "audit_output=$output"
Get-Content -Raw -Encoding utf8 (Join-Path $output "tool_exit_codes.json")
if ($blockerFailures.Count -ne 0) {
    exit 1
}
