param(
    [string]$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\.."))
)

$ErrorActionPreference = "Stop"
$utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8
$env:PYTHONUTF8 = "1"
$root = (Resolve-Path $RepositoryRoot).Path
$pythonLauncher = (Get-Command py.exe -ErrorAction Stop).Source

$projects = @(
    @{ Name = "e00"; DirectoryName = "os_network_reference" },
    @{ Name = "e01"; DirectoryName = "concurrency_reference" },
    @{ Name = "p01"; DirectoryName = "mini_scheduler" },
    @{ Name = "e02"; DirectoryName = "e02_service" },
    @{ Name = "e03"; DirectoryName = "e03_rag_reference" },
    @{ Name = "e04"; DirectoryName = "e04_runtime_reference" },
    @{ Name = "e06"; DirectoryName = "e06_sqlite_reference" },
    @{ Name = "e10"; DirectoryName = "e10_inference_reference" },
    @{ Name = "finance"; DirectoryName = "finance_reference" },
    @{ Name = "p03"; DirectoryName = "p03_service" }
)

$lockFiles = @(
    Get-ChildItem -LiteralPath $root -Recurse -File -Filter "requirements-dev.lock" |
        Where-Object { $_.FullName -notmatch "[\\/](?:\.venv|\.tools)[\\/]" }
)

if ($lockFiles.Count -ne $projects.Count) {
    throw "expected $($projects.Count) reference lock files, found $($lockFiles.Count)"
}

& $pythonLauncher -3.13 -c `
    "import sys; assert sys.version_info[:2] == (3, 13), sys.version"
if ($LASTEXITCODE -ne 0) {
    throw "Python 3.13 is required"
}

foreach ($project in $projects) {
    $matches = @(
        $lockFiles | Where-Object { $_.Directory.Name -eq $project.DirectoryName }
    )
    if ($matches.Count -ne 1) {
        throw "$($project.Name) expected one lock file, found $($matches.Count)"
    }
    $lockFile = $matches[0].FullName
    $projectRoot = $matches[0].Directory.FullName
    $venvRoot = Join-Path $projectRoot ".venv"
    $python = Join-Path $venvRoot "Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        & $pythonLauncher -3.13 -m venv $venvRoot
        if ($LASTEXITCODE -ne 0) {
            throw "$($project.Name) virtual environment creation failed"
        }
    }

    $pythonVersion = (& $python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')").Trim()
    if ($LASTEXITCODE -ne 0 -or $pythonVersion -ne "3.13") {
        throw "$($project.Name) virtual environment uses Python $pythonVersion; expected 3.13"
    }

    & $python -m pip install `
        --disable-pip-version-check `
        --requirement $lockFile
    if ($LASTEXITCODE -ne 0) {
        throw "$($project.Name) dependency installation failed"
    }
    & $python -m pip check
    if ($LASTEXITCODE -ne 0) {
        throw "$($project.Name) dependency consistency check failed"
    }
    Write-Output "reference_env_ready=$($project.Name)"
}

Write-Output "reference_env_count=$($projects.Count)"
