param(
    [string]$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")),
    [switch]$SkipContentAudit,
    [switch]$SkipMermaid
)

$ErrorActionPreference = "Stop"
$utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8
$env:PYTHONUTF8 = "1"
$root = (Resolve-Path $RepositoryRoot).Path
$dateStamp = Get-Date -Format "yyyy-MM-dd"
$output = Join-Path $root "00_路线总控\审计与整改\artifacts\full_validation_$dateStamp"
$contentAuditOutput = Join-Path $root "00_路线总控\审计与整改\artifacts\content_quality_audit_$dateStamp"
$summaryName = if ($SkipContentAudit -or $SkipMermaid) {
    "summary_smoke.json"
} else {
    "summary.json"
}
$summaryPath = Join-Path $output $summaryName
$summaryRelativePaths = @(
    (Join-Path $output "summary.json").Substring($root.Length).TrimStart("\").Replace("\", "/"),
    (Join-Path $output "summary_smoke.json").Substring($root.Length).TrimStart("\").Replace("\", "/")
)
$generatedEvidenceRelativePaths = @(
    $output.Substring($root.Length).TrimStart("\").Replace("\", "/"),
    $contentAuditOutput.Substring($root.Length).TrimStart("\").Replace("\", "/")
)
$generatedEvidencePrefixes = @($generatedEvidenceRelativePaths | ForEach-Object { "$_/" })
$generatedEvidenceExclusionPathspecs = @(
    $generatedEvidenceRelativePaths | ForEach-Object { ":(exclude)$_/**" }
)

function Remove-StaleGeneratedEvidence {
    $previousPreference = $ErrorActionPreference
    Push-Location $root
    try {
        $ErrorActionPreference = "Continue"
        $trackedEvidenceFiles = @()
        foreach ($relativePath in $generatedEvidenceRelativePaths) {
            $trackedEvidenceFiles += @(& git -c core.quotepath=false ls-files -- $relativePath)
            if ($LASTEXITCODE -ne 0) {
                throw "cannot enumerate tracked validation evidence: $relativePath"
            }
        }

        foreach ($directory in @($output, $contentAuditOutput)) {
            if (Test-Path -LiteralPath $directory) {
                Remove-Item -LiteralPath $directory -Recurse -Force -ErrorAction Stop
            }
            if (Test-Path -LiteralPath $directory) {
                throw "stale validation evidence directory still exists after cleanup: $directory"
            }
        }

        foreach ($trackedPath in @($trackedEvidenceFiles | Select-Object -Unique)) {
            & git update-index --force-remove -- $trackedPath 2>$null
            if ($LASTEXITCODE -ne 0) {
                throw "failed to stage stale validation evidence removal: $trackedPath"
            }
        }
    } finally {
        $ErrorActionPreference = $previousPreference
        Pop-Location
    }
}

function Remove-StaleValidationSummary {
    foreach ($summary in $summaryRelativePaths) {
        $summaryAbsolutePath = Join-Path $root $summary
        if (Test-Path -LiteralPath $summaryAbsolutePath) {
            Remove-Item -LiteralPath $summaryAbsolutePath -Force
        }
    }

    Push-Location $root
    try {
        $previousPreference = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        foreach ($summary in $summaryRelativePaths) {
            & git update-index --force-remove -- $summary 2>$null
            $removeIndexExit = $LASTEXITCODE
            if ($removeIndexExit -ne 0) {
                throw "failed to remove stale validation summary from the Git index: $summary"
            }
        }
        $ErrorActionPreference = $previousPreference
    } finally {
        $ErrorActionPreference = "Stop"
        Pop-Location
    }
}

Remove-StaleGeneratedEvidence

Push-Location $root
try {
    & git diff --quiet --exit-code
    if ($LASTEXITCODE -ne 0) {
        throw "unstaged tracked changes detected; stage the release candidate before validation"
    }
    $untracked = @(& git -c core.quotepath=false ls-files --others --exclude-standard)
    if ($LASTEXITCODE -ne 0) {
        throw "cannot enumerate untracked release-candidate files"
    }
    $untrackedCandidate = @(
        $untracked | Where-Object {
            $path = $_.Replace("\", "/")
            -not ($generatedEvidencePrefixes | Where-Object { $path.StartsWith($_) })
        }
    )
    if ($untrackedCandidate.Count -gt 0) {
        throw "untracked release-candidate files detected; stage or ignore them before validation: $($untrackedCandidate -join ', ')"
    }
} catch {
    Remove-StaleValidationSummary
    throw
} finally {
    Pop-Location
}

Remove-StaleValidationSummary
New-Item -ItemType Directory -Force -Path $output | Out-Null
$pythonLauncher = (Get-Command py.exe).Source

function Convert-LogToUtf8 {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (Test-Path -LiteralPath $Path) {
        $content = [IO.File]::ReadAllText($Path)
        [IO.File]::WriteAllText($Path, $content, $utf8)
    }
}

function Convert-ValidationArtifactsToPortable {
    param(
        [Parameter(Mandatory = $true)][string]$Directory,
        [Parameter(Mandatory = $true)][string]$RepositoryRoot
    )

    $machinePaths = @(
        @{ Value = $RepositoryRoot; Placeholder = "<repository>" },
        @{ Value = ([IO.Path]::GetTempPath().TrimEnd("\")); Placeholder = "<temp>" },
        @{ Value = $env:LOCALAPPDATA; Placeholder = "<local-app-data>" },
        @{ Value = $env:APPDATA; Placeholder = "<app-data>" },
        @{ Value = $env:USERPROFILE; Placeholder = "<user-profile>" }
    )
    $replacementPairs = @{}
    foreach ($machinePath in $machinePaths) {
        $value = [string]$machinePath.Value
        if ([string]::IsNullOrWhiteSpace($value)) {
            continue
        }
        foreach ($form in @(
            $value,
            $value.Replace("\", "\\"),
            $value.Replace("\", "/")
        )) {
            if (-not $replacementPairs.ContainsKey($form)) {
                $replacementPairs[$form] = [string]$machinePath.Placeholder
            }
        }
    }

    Get-ChildItem -LiteralPath $Directory -Recurse -File | Where-Object {
        $_.Extension -in @(".csv", ".json", ".log", ".md", ".txt", ".xml")
    } | ForEach-Object {
        $content = [IO.File]::ReadAllText($_.FullName)
        $portable = $content
        foreach ($pair in $replacementPairs.GetEnumerator() | Sort-Object { $_.Key.Length } -Descending) {
            $portable = $portable.Replace([string]$pair.Key, [string]$pair.Value)
        }
        $portable = $portable.Replace("\\?\<repository>", "<repository>")
        $portable = $portable.Replace("//?/<repository>", "<repository>")
        if ($portable -ne $content) {
            [IO.File]::WriteAllText($_.FullName, $portable, $utf8)
        }
    }
}

function Assert-NoMachineLocalPathsInStagedTree {
    param([Parameter(Mandatory = $true)][string]$RepositoryRoot)

    $pathForms = New-Object System.Collections.Generic.List[string]
    $machinePaths = @(
        $RepositoryRoot,
        $env:USERPROFILE,
        $env:LOCALAPPDATA,
        $env:APPDATA,
        ([IO.Path]::GetTempPath().TrimEnd("\"))
    )
    foreach ($machinePath in $machinePaths) {
        if ([string]::IsNullOrWhiteSpace($machinePath)) {
            continue
        }
        foreach ($pathForm in @(
            $machinePath,
            $machinePath.Replace("\", "\\"),
            $machinePath.Replace("\", "/")
        )) {
            if (-not $pathForms.Contains($pathForm)) {
                $pathForms.Add($pathForm)
            }
        }
    }

    $violations = @()
    $previousPreference = $ErrorActionPreference
    Push-Location $RepositoryRoot
    try {
        $ErrorActionPreference = "Continue"
        foreach ($pathForm in $pathForms) {
            $matches = @(& git grep --cached -n -I -F -e $pathForm -- 2>$null)
            $grepExit = $LASTEXITCODE
            if ($grepExit -eq 0) {
                $violations += $matches
            } elseif ($grepExit -ne 1) {
                throw "failed to scan the staged tree for machine-local paths"
            }
        }
    } finally {
        $ErrorActionPreference = $previousPreference
        Pop-Location
    }

    if ($violations.Count -gt 0) {
        $sample = @($violations | Select-Object -Unique | Select-Object -First 20)
        throw "staged release candidate contains machine-local paths`n$($sample -join [Environment]::NewLine)"
    }
}

$encodingPreflightLog = Join-Path $output "encoding_preflight.log"
$encodingPreflightJson = Join-Path $output "encoding_preflight.json"
& $pythonLauncher -3.13 `
    (Join-Path $PSScriptRoot "validate_encoding.py") $root `
    --json-output $encodingPreflightJson 2>&1 |
    Tee-Object -FilePath $encodingPreflightLog
$encodingPreflightExit = $LASTEXITCODE
Convert-LogToUtf8 -Path $encodingPreflightLog
if ($encodingPreflightExit -ne 0) {
    throw "encoding preflight failed"
}

$projects = @(
    @{ Name = "e00"; Path = "40_实验练习\E00_工具链基础实验\os_network_reference"; ExpectedTests = 11 },
    @{ Name = "e01"; Path = "40_实验练习\E01_Python基础练习\concurrency_reference"; ExpectedTests = 6 },
    @{ Name = "e02"; Path = "40_实验练习\E02_后端API实验\e02_service"; ExpectedTests = 29 },
    @{ Name = "e03"; Path = "40_实验练习\E03_RAG实验\e03_rag_reference"; ExpectedTests = 154 },
    @{ Name = "e04"; Path = "40_实验练习\E04_Agent实验\e04_runtime_reference"; ExpectedTests = 86 },
    @{ Name = "e06"; Path = "40_实验练习\E06_数据库异步任务实验\e06_sqlite_reference"; ExpectedTests = 42 },
    @{ Name = "e10"; Path = "40_实验练习\E10_推理服务实验\e10_inference_reference"; ExpectedTests = 7 },
    @{ Name = "p01"; Path = "50_项目产出\P01_Mini_Scheduler\mini_scheduler"; ExpectedTests = 28 },
    @{ Name = "finance"; Path = "40_实验练习\GF10_金融工程全阶段实验候选\finance_reference"; ExpectedTests = 9 },
    @{ Name = "p03"; Path = "50_项目产出\P03_AI_Workload_Platform\p03_service"; ExpectedTests = 27 }
)
$expectedReferenceTestTotal = [int](
    ($projects | ForEach-Object { [int]$_["ExpectedTests"] } | Measure-Object -Sum).Sum
)

$testCounts = [ordered]@{}
foreach ($project in $projects) {
    $projectRoot = Join-Path $root $project.Path
    $python = Join-Path $projectRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $python)) {
        throw "$($project.Name) virtual environment is missing: $python"
    }
    $pythonVersion = (& $python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')").Trim()
    if ($LASTEXITCODE -ne 0 -or $pythonVersion -ne "3.13") {
        throw "$($project.Name) virtual environment uses Python $pythonVersion; expected 3.13"
    }
    $junitPath = Join-Path ([IO.Path]::GetTempPath()) (
        "ai-infra-$($project.Name)-{0}.xml" -f [guid]::NewGuid().ToString("N")
    )
    Push-Location $projectRoot
    try {
        & $python -X dev -W "error::ResourceWarning" -m pytest -q --junitxml=$junitPath 2>&1 |
            Tee-Object -FilePath (Join-Path $output "$($project.Name)_pytest.log")
        $projectExit = $LASTEXITCODE
        Convert-LogToUtf8 -Path (Join-Path $output "$($project.Name)_pytest.log")
        if ($projectExit -ne 0) {
            throw "$($project.Name) pytest failed"
        }
        [xml]$junit = Get-Content -LiteralPath $junitPath -Raw -Encoding utf8
        $suite = $junit.testsuites.testsuite
        $testCount = [int]$suite.tests
        $failureCount = [int]$suite.failures
        $errorCount = [int]$suite.errors
        $skippedCount = [int]$suite.skipped
        if ($testCount -ne [int]$project.ExpectedTests) {
            throw "$($project.Name) collected $testCount tests; expected $($project.ExpectedTests)"
        }
        if ($failureCount -ne 0 -or $errorCount -ne 0 -or $skippedCount -ne 0) {
            throw "$($project.Name) JUnit result is not clean: failures=$failureCount errors=$errorCount skipped=$skippedCount"
        }
        $testCounts[$project.Name] = $testCount
    } finally {
        Pop-Location
        Remove-Item -LiteralPath $junitPath -Force -ErrorAction SilentlyContinue
    }
}
$referenceTestTotal = [int](($testCounts.Values | Measure-Object -Sum).Sum)
if ($referenceTestTotal -ne $expectedReferenceTestTotal) {
    throw "reference test total is $referenceTestTotal; expected $expectedReferenceTestTotal"
}

$governanceValidators = @(
    "validate_file_matrix.py",
    "validate_optimization_matrix.py",
    "validate_provenance_ledger.py",
    "validate_rq01_artifacts.py",
    "validate_version_manifest.py"
)

foreach ($validator in $governanceValidators) {
    $validatorName = [IO.Path]::GetFileNameWithoutExtension($validator)
    $validatorLog = Join-Path $output "$validatorName.log"
    & $pythonLauncher -3.13 (Join-Path $PSScriptRoot $validator) $root 2>&1 |
        Tee-Object -FilePath $validatorLog
    $validatorExit = $LASTEXITCODE
    Convert-LogToUtf8 -Path $validatorLog
    if ($validatorExit -ne 0) {
        throw "$validatorName failed"
    }
}
$versionManifestPath = Join-Path $root "00_路线总控\审计与整改\artifacts\governance\version_manifest.json"
$versionManifest = Get-Content -LiteralPath $versionManifestPath -Raw -Encoding utf8 |
    ConvertFrom-Json
$versionManifestComponentCount = @($versionManifest.components).Count
$provenanceLedgerPath = Join-Path $root "00_路线总控\审计与整改\artifacts\governance\provenance_license_ledger.csv"
$provenanceRows = @(Import-Csv -LiteralPath $provenanceLedgerPath -Encoding utf8)
$provenanceReviewRequiredCount = @(
    $provenanceRows | Where-Object { $_.review_status -eq "review-required" }
).Count
$provenanceVerifiedCount = @(
    $provenanceRows | Where-Object { $_.review_status -eq "verified" }
).Count

$powerShellSyntaxErrors = @()
$powerShellScriptCount = 0
$scriptExcludePattern = "[\\/](?:\.git|\.obsidian|\.tools|\.venv|__pycache__|\.pytest_cache)(?:[\\/]|$)"
foreach ($script in Get-ChildItem -LiteralPath $root -Recurse -File -Filter "*.ps1") {
    if ($script.FullName -match $scriptExcludePattern) {
        continue
    }
    $powerShellScriptCount += 1
    $tokens = $null
    $parseErrors = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile(
        $script.FullName,
        [ref]$tokens,
        [ref]$parseErrors
    )
    foreach ($parseError in $parseErrors) {
        $relativeScript = $script.FullName.Substring($root.Length).TrimStart("\")
        $powerShellSyntaxErrors += "${relativeScript}:$($parseError.Extent.StartLineNumber): $($parseError.Message)"
    }
}
if ($powerShellSyntaxErrors.Count -gt 0) {
    throw "PowerShell syntax validation failed`n$($powerShellSyntaxErrors -join [Environment]::NewLine)"
}

$composeFile = Join-Path $root "50_项目产出\P03_AI_Workload_Platform\p03_service\compose.yaml"
& docker compose -f $composeFile config --quiet
if ($LASTEXITCODE -ne 0) {
    throw "docker compose config validation failed"
}

$kustomizeDirectory = Join-Path $root "40_实验练习\E09_K8s实验\kind_reference\manifests"
& kubectl kustomize $kustomizeDirectory | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "kubectl kustomize validation failed"
}

$repositoryLog = Join-Path $output "repository_validator.log"
& $pythonLauncher -3.13 `
    (Join-Path $PSScriptRoot "validate_repository.py") $root 2>&1 |
    Tee-Object -FilePath $repositoryLog
$repositoryExit = $LASTEXITCODE
Convert-LogToUtf8 -Path $repositoryLog
if ($repositoryExit -ne 0) {
    throw "repository validator failed"
}

if (-not $SkipContentAudit) {
    & (Join-Path $PSScriptRoot "content_quality\run_content_quality_audit.ps1") `
        -RepositoryRoot $root `
        -OutputDirectory "00_路线总控\审计与整改\artifacts\content_quality_audit_$dateStamp" `
        2>&1 | Tee-Object -FilePath (Join-Path $output "content_quality_audit.log")
    $contentAuditExit = $LASTEXITCODE
    Convert-LogToUtf8 -Path (Join-Path $output "content_quality_audit.log")
    if ($contentAuditExit -ne 0) {
        throw "content quality blocker failed"
    }
}
$contentAuditStatus = "skipped"
$contentAuditAdvisories = @()
if (-not $SkipContentAudit) {
    $contentAuditSummaryPath = Join-Path $root (
        "00_路线总控\审计与整改\artifacts\content_quality_audit_$dateStamp\tool_exit_codes.json"
    )
    $contentAuditSummary = Get-Content -LiteralPath $contentAuditSummaryPath -Raw -Encoding utf8 |
        ConvertFrom-Json
    $contentAuditStatus = $contentAuditSummary.audit_status
    $contentAuditAdvisories = @($contentAuditSummary.advisory_nonzero)
}

if (-not $SkipMermaid) {
    & (Join-Path $PSScriptRoot "content_quality\validate_mermaid.ps1") `
        -RepositoryRoot $root `
        -ReportPath "00_路线总控\审计与整改\artifacts\content_quality_audit_$dateStamp\mermaid_validation.json" `
        2>&1 |
        Tee-Object -FilePath (Join-Path $output "mermaid.log")
    $mermaidExit = $LASTEXITCODE
    Convert-LogToUtf8 -Path (Join-Path $output "mermaid.log")
    if ($mermaidExit -ne 0) {
        throw "Mermaid render validation failed"
    }
}

$structuredDataLog = Join-Path $output "validate_structured_data.log"
& $pythonLauncher -3.13 (Join-Path $PSScriptRoot "validate_structured_data.py") $root 2>&1 |
    Tee-Object -FilePath $structuredDataLog
$structuredDataExit = $LASTEXITCODE
Convert-LogToUtf8 -Path $structuredDataLog
if ($structuredDataExit -ne 0) {
    throw "structured data validation failed"
}

$compileExclude = "[\\/](?:\.venv|\.tools|node_modules|__pycache__)[\\/]"
$compileLog = Join-Path $output "compileall.log"
& $pythonLauncher -3.13 -m compileall -q -x $compileExclude $root 2>&1 |
    Tee-Object -FilePath $compileLog
$compileExit = $LASTEXITCODE
Convert-LogToUtf8 -Path $compileLog
if ($compileExit -ne 0) {
    throw "Python compileall failed"
}
$compileEvidence = if (Test-Path -LiteralPath $compileLog) {
    [IO.File]::ReadAllText($compileLog)
} else {
    ""
}
[IO.File]::WriteAllText($compileLog, $compileEvidence + "compileall=passed`n", $utf8)

$encodingLog = Join-Path $output "encoding_validation.log"
$encodingJson = Join-Path $output "encoding_validation.json"
& $pythonLauncher -3.13 `
    (Join-Path $PSScriptRoot "validate_encoding.py") $root `
    --json-output $encodingJson 2>&1 |
    Tee-Object -FilePath $encodingLog
$encodingExit = $LASTEXITCODE
Convert-LogToUtf8 -Path $encodingLog
if ($encodingExit -ne 0) {
    throw "final encoding validation failed"
}

Push-Location $root
try {
    $structuredDataFinalLog = Join-Path $output "validate_structured_data_final.log"
    & $pythonLauncher -3.13 (Join-Path $PSScriptRoot "validate_structured_data.py") $root 2>&1 |
        Tee-Object -FilePath $structuredDataFinalLog
    $structuredDataFinalExit = $LASTEXITCODE
    Convert-LogToUtf8 -Path $structuredDataFinalLog
    if ($structuredDataFinalExit -ne 0) {
        throw "final structured data validation failed"
    }

    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"

    $generatedEvidencePaths = @(
        "00_路线总控\审计与整改\artifacts\full_validation_$dateStamp",
        "00_路线总控\审计与整改\artifacts\content_quality_audit_$dateStamp"
    )
    foreach ($generatedPath in $generatedEvidencePaths) {
        $generatedAbsolutePath = Join-Path $root $generatedPath
        if (Test-Path -LiteralPath $generatedAbsolutePath) {
            Convert-ValidationArtifactsToPortable `
                -Directory $generatedAbsolutePath `
                -RepositoryRoot $root
            & git add -f -A -- $generatedPath
            if ($LASTEXITCODE -ne 0) {
                throw "failed to stage generated validation evidence: $generatedPath"
            }

            $trackedGeneratedPaths = @(& git -c core.quotepath=false ls-files -- $generatedPath)
            if ($LASTEXITCODE -ne 0) {
                throw "cannot enumerate staged validation evidence: $generatedPath"
            }
            $trackedGeneratedSet = @{}
            foreach ($trackedGeneratedPath in $trackedGeneratedPaths) {
                $trackedGeneratedSet[$trackedGeneratedPath.Replace("\", "/")] = $true
            }
            $missingGeneratedPaths = @(
                Get-ChildItem -LiteralPath $generatedAbsolutePath -Recurse -File |
                    ForEach-Object {
                        $_.FullName.Substring($root.Length).TrimStart("\").Replace("\", "/")
                    } |
                    Where-Object { -not $trackedGeneratedSet.ContainsKey($_) }
            )
            if ($missingGeneratedPaths.Count -gt 0) {
                throw "generated validation evidence is not tracked: $($missingGeneratedPaths -join ', ')"
            }
        }
    }
    Assert-NoMachineLocalPathsInStagedTree -RepositoryRoot $root

    $gitleaks = Join-Path $root ".tools\content-quality\gitleaks\8.30.1\gitleaks.exe"
    if (-not (Test-Path -LiteralPath $gitleaks)) {
        throw "gitleaks executable is missing: $gitleaks"
    }
    $gitleaksHistoryReport = Join-Path ([IO.Path]::GetTempPath()) (
        "ai-infra-gitleaks-history-{0}.json" -f [guid]::NewGuid().ToString("N")
    )
    $gitleaksStagedReport = Join-Path ([IO.Path]::GetTempPath()) (
        "ai-infra-gitleaks-release-candidate-{0}.json" -f [guid]::NewGuid().ToString("N")
    )
    try {
        & $gitleaks git $root --log-opts="--all" --max-archive-depth 2 `
            --no-banner --no-color --redact=100 --report-format json --report-path $gitleaksHistoryReport
        if ($LASTEXITCODE -ne 0) {
            throw "reachable-history secret scan failed"
        }
        & $gitleaks git $root --staged --max-archive-depth 2 --no-banner --no-color --redact=100 `
            --report-format json --report-path $gitleaksStagedReport
        if ($LASTEXITCODE -ne 0) {
            throw "staged release-candidate secret scan failed"
        }
    } finally {
        Remove-Item -LiteralPath $gitleaksHistoryReport -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $gitleaksStagedReport -Force -ErrorAction SilentlyContinue
    }

    $untrackedAfterValidation = @(& git -c core.quotepath=false ls-files --others --exclude-standard)
    if ($LASTEXITCODE -ne 0) {
        throw "cannot enumerate untracked files after validation"
    }
    if ($untrackedAfterValidation.Count -gt 0) {
        throw "validation created untracked release candidates: $($untrackedAfterValidation -join ', ')"
    }

    & git diff --quiet --exit-code
    if ($LASTEXITCODE -ne 0) {
        throw "validation left unstaged tracked changes outside the sealed evidence paths"
    }

    # Raw validator logs intentionally preserve diagnostics such as trailing-space
    # findings. Keep source whitespace checks strict without rewriting that evidence.
    $gitChecks = @(
        @{
            Name = "worktree"
            Arguments = @("diff", "--check", "--", ".") + $generatedEvidenceExclusionPathspecs
        },
        @{
            Name = "index"
            Arguments = @("diff", "--cached", "--check", "--", ".") + $generatedEvidenceExclusionPathspecs
        }
    )
    foreach ($check in $gitChecks) {
        $checkOutput = & git @($check.Arguments) 2>&1
        $checkExit = $LASTEXITCODE
        if ($checkExit -ne 0) {
            throw "git $($check.Name) diff --check failed`n$($checkOutput -join [Environment]::NewLine)"
        }
    }

    $realIndexTree = (& git write-tree).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($realIndexTree)) {
        throw "failed to write the sealed Git index tree"
    }

    $temporaryIndex = Join-Path ([IO.Path]::GetTempPath()) (
        "ai-infra-release-candidate-{0}.index" -f [guid]::NewGuid().ToString("N")
    )
    $previousGitIndexFile = $env:GIT_INDEX_FILE
    try {
        $env:GIT_INDEX_FILE = $temporaryIndex
        & git read-tree HEAD
        if ($LASTEXITCODE -ne 0) {
            throw "temporary release-candidate index initialization failed"
        }
        & git add -A -- .
        if ($LASTEXITCODE -ne 0) {
            throw "temporary release-candidate staging failed"
        }
        foreach ($generatedPath in $generatedEvidenceRelativePaths) {
            $generatedAbsolutePath = Join-Path $root $generatedPath
            if (Test-Path -LiteralPath $generatedAbsolutePath) {
                & git add -f -A -- $generatedPath
                if ($LASTEXITCODE -ne 0) {
                    throw "temporary validation evidence staging failed: $generatedPath"
                }
            }
        }

        $candidateDiffArguments = @("diff", "--cached", "--check", "--", ".") +
            $generatedEvidenceExclusionPathspecs
        $candidateOutput = & git @candidateDiffArguments 2>&1
        $candidateExit = $LASTEXITCODE
        if ($candidateExit -ne 0) {
            throw "release-candidate git diff --check failed`n$($candidateOutput -join [Environment]::NewLine)"
        }
        $temporaryIndexTree = (& git write-tree).Trim()
        if ($LASTEXITCODE -ne 0 -or $temporaryIndexTree -ne $realIndexTree) {
            throw "sealed index tree does not match the complete working-tree candidate"
        }
    } finally {
        if ([string]::IsNullOrEmpty($previousGitIndexFile)) {
            Remove-Item Env:GIT_INDEX_FILE -ErrorAction SilentlyContinue
        } else {
            $env:GIT_INDEX_FILE = $previousGitIndexFile
        }
        Remove-Item -LiteralPath $temporaryIndex -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath "$temporaryIndex.lock" -Force -ErrorAction SilentlyContinue
    }

    $ErrorActionPreference = $previousErrorActionPreference
} catch {
    Remove-StaleValidationSummary
    throw
} finally {
    $ErrorActionPreference = "Stop"
    Pop-Location
}

# Write the green summary only after the sealed index, candidate tree, and secret scan pass.
[ordered]@{
    status = "passed"
    encoding_validation = "passed"
    governance_validation = "passed"
    version_manifest_component_count = $versionManifestComponentCount
    provenance_inventory_status = if ($provenanceReviewRequiredCount -eq 0) {
        "fully-reviewed"
    } else {
        "review-required"
    }
    provenance_row_count = $provenanceRows.Count
    provenance_verified_count = $provenanceVerifiedCount
    provenance_review_required_count = $provenanceReviewRequiredCount
    structured_data_validation = "passed"
    rq01_artifact_validation = "passed"
    powershell_syntax_validation = "passed"
    powershell_script_count = $powerShellScriptCount
    compose_config_validation = "passed"
    kustomize_validation = "passed"
    compileall_validation = "passed"
    git_release_candidate_validation = "passed"
    generated_evidence_tracking = "passed"
    machine_local_path_scan = "passed"
    staged_secret_scan = "passed"
    reference_python_version = "3.13"
    reference_project_count = $projects.Count
    reference_test_count = $referenceTestTotal
    reference_test_counts = $testCounts
    content_audit_skipped = [bool]$SkipContentAudit
    content_audit_status = $contentAuditStatus
    content_audit_advisories = $contentAuditAdvisories
    mermaid_skipped = [bool]$SkipMermaid
    mermaid_validation = if ($SkipMermaid) { "skipped" } else { "passed" }
    completed_at_utc = [DateTime]::UtcNow.ToString("o")
} | ConvertTo-Json | ForEach-Object {
    [IO.File]::WriteAllText($summaryPath, $_ + [Environment]::NewLine, $utf8)
}

# The summary is created after the first sealed-tree check, so seal it and recheck the final candidate.
$summaryRelativePath = $summaryPath.Substring($root.Length).TrimStart("\")
Push-Location $root
try {
    & git add -A -- $summaryRelativePath
    if ($LASTEXITCODE -ne 0) {
        throw "failed to stage final validation summary"
    }
    Assert-NoMachineLocalPathsInStagedTree -RepositoryRoot $root

    $postSummaryUntracked = @(& git -c core.quotepath=false ls-files --others --exclude-standard)
    if ($LASTEXITCODE -ne 0 -or $postSummaryUntracked.Count -gt 0) {
        throw "final summary sealing left untracked release candidates: $($postSummaryUntracked -join ', ')"
    }
    & git diff --quiet --exit-code
    if ($LASTEXITCODE -ne 0) {
        throw "final summary sealing left unstaged tracked changes"
    }
    $postSummaryDiffArguments = @("diff", "--cached", "--check", "--", ".") +
        $generatedEvidenceExclusionPathspecs
    $postSummaryDiff = & git @postSummaryDiffArguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "final summary staged diff check failed`n$($postSummaryDiff -join [Environment]::NewLine)"
    }

    $postSummaryReport = Join-Path ([IO.Path]::GetTempPath()) (
        "ai-infra-gitleaks-final-summary-{0}.json" -f [guid]::NewGuid().ToString("N")
    )
    try {
        & $gitleaks git $root --staged --max-archive-depth 2 --no-banner --no-color --redact=100 `
            --report-format json --report-path $postSummaryReport
        if ($LASTEXITCODE -ne 0) {
            throw "final summary staged secret scan failed"
        }
    } finally {
        Remove-Item -LiteralPath $postSummaryReport -Force -ErrorAction SilentlyContinue
    }

    $postSummaryTree = (& git write-tree).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($postSummaryTree)) {
        throw "failed to write final summary sealed index tree"
    }
} catch {
    Remove-StaleValidationSummary
    throw
} finally {
    Pop-Location
}

Write-Output "full_validation=passed"
Write-Output "validation_output=$output"
