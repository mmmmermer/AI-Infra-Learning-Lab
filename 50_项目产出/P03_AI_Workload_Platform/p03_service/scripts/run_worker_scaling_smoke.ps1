[CmdletBinding()]
param(
    [int[]] $WorkerCounts = @(1, 2, 4),
    [int] $Users = 5,
    [int] $SpawnRate = 5,
    [string] $RunTime = "8s",
    [int] $SleepMs = 25,
    [double] $RequestsPerUser = 5
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ArtifactRoot = Join-Path $ProjectRoot "artifacts\e08_reference_smoke"
$rows = @()

function Get-WeightedPercentile {
    param(
        [Parameter(Mandatory)] [object] $ResponseTimes,
        [Parameter(Mandatory)] [double] $Quantile
    )
    $buckets = @(
        $ResponseTimes.PSObject.Properties |
            ForEach-Object {
                [pscustomobject]@{
                    response_time = [double]$_.Name
                    count = [int]$_.Value
                }
            } |
            Sort-Object response_time
    )
    $total = ($buckets | Measure-Object count -Sum).Sum
    $target = [Math]::Ceiling($total * $Quantile)
    $seen = 0
    foreach ($bucket in $buckets) {
        $seen += $bucket.count
        if ($seen -ge $target) {
            return $bucket.response_time
        }
    }
    return $null
}

try {
foreach ($workerCount in $WorkerCounts) {
    Push-Location $ProjectRoot
    try {
        docker compose down -v --remove-orphans | Out-Host
        docker compose up -d --scale worker=$workerCount | Out-Host
        if ($LASTEXITCODE -ne 0) {
            throw "Compose startup failed for worker_count=$workerCount"
        }

        $label = "workers_$workerCount"
        & (Join-Path $PSScriptRoot "run_load_smoke.ps1") `
            -Users $Users `
            -SpawnRate $SpawnRate `
            -RunTime $RunTime `
            -WorkerCount $workerCount `
            -SleepMs $SleepMs `
            -RequestsPerUser $RequestsPerUser `
            -Label $label

        $summary = Get-Content `
            -Raw `
            -Encoding UTF8 `
            (Join-Path $ArtifactRoot "$label\run_summary.json") | ConvertFrom-Json
        $csvStats = Import-Csv (Join-Path $ArtifactRoot "$label\locust_stats.csv") |
            Where-Object { $_.Type -eq "POST" } |
            Select-Object -First 1
        $finalStats = Get-Content `
            -Raw `
            -Encoding UTF8 `
            (Join-Path $ArtifactRoot "$label\locust_final.json") | ConvertFrom-Json |
            Where-Object { $_.method -eq "POST" -and $_.name -eq "POST /tasks" } |
            Select-Object -First 1
        $rows += [pscustomobject]@{
            worker_count = $workerCount
            task_count = $summary.metrics.task_count
            api_requests_per_second = [double]$csvStats.'Requests/s'
            api_p95_ms = Get-WeightedPercentile $finalStats.response_times 0.95
            api_p99_ms = Get-WeightedPercentile $finalStats.response_times 0.99
            api_failure_count = [int]$finalStats.num_failures
            average_queue_wait_ms = [double]$summary.metrics.average_queue_wait_ms
            p95_queue_wait_ms = [double]$summary.metrics.p95_queue_wait_ms
            p99_queue_wait_ms = [double]$summary.metrics.p99_queue_wait_ms
            p95_runtime_ms = [double]$summary.metrics.p95_runtime_ms
            task_processing_utilization = [double]$summary.task_processing_utilization
            observation_window_ms = [double]$summary.metrics.observation_window_ms
        }
    }
    finally {
        Pop-Location
    }
}

$summaryPath = Join-Path $ArtifactRoot "worker_scaling_summary.csv"
$rows | Export-Csv -NoTypeInformation -Encoding UTF8 $summaryPath
$rows | Format-Table -AutoSize
}
finally {
    Push-Location $ProjectRoot
    try {
        docker compose down -v --remove-orphans | Out-Host
    }
    finally {
        Pop-Location
    }
}
