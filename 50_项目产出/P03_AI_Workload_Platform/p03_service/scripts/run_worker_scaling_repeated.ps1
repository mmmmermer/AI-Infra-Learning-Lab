[CmdletBinding()]
param(
    [int[]] $WorkerCounts = @(1, 2, 4),
    [int] $Repeats = 3,
    [int] $Users = 5,
    [int] $SpawnRate = 5,
    [string] $RunTime = "8s",
    [ValidateSet("mock_rag", "rag_retrieval")]
    [string] $TaskType = "mock_rag",
    [int] $SleepMs = 25,
    [int] $TopK = 3,
    [double] $RequestsPerUser = 5,
    [int] $SampleIntervalMilliseconds = 500,
    [int] $ResourceSampleIntervalMilliseconds = 2000,
    [int] $RandomSeed = 20260711
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ArtifactRootName = "e08_reference_repeated"
$ArtifactRoot = Join-Path $ProjectRoot "artifacts\$ArtifactRootName"
$rows = @()

if ($Repeats -lt 3) {
    throw "At least three repeats are required for the reference confidence interval"
}
if ($WorkerCounts.Count -lt 2) {
    throw "Provide at least two worker counts"
}
New-Item -ItemType Directory -Force $ArtifactRoot | Out-Null

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

function Get-TCritical95 {
    param([Parameter(Mandatory)] [int] $DegreesOfFreedom)
    $values = @{
        1 = 12.706; 2 = 4.303; 3 = 3.182; 4 = 2.776; 5 = 2.571
        6 = 2.447; 7 = 2.365; 8 = 2.306; 9 = 2.262; 10 = 2.228
        11 = 2.201; 12 = 2.179; 13 = 2.160; 14 = 2.145; 15 = 2.131
        16 = 2.120; 17 = 2.110; 18 = 2.101; 19 = 2.093; 20 = 2.086
        21 = 2.080; 22 = 2.074; 23 = 2.069; 24 = 2.064; 25 = 2.060
        26 = 2.056; 27 = 2.052; 28 = 2.048; 29 = 2.045; 30 = 2.042
    }
    if ($values.ContainsKey($DegreesOfFreedom)) {
        return [double]$values[$DegreesOfFreedom]
    }
    return 1.96
}

function Get-ConfidenceSummary {
    param([Parameter(Mandatory)] [double[]] $Values)
    $count = $Values.Count
    $mean = ($Values | Measure-Object -Average).Average
    $sumSquares = 0.0
    foreach ($value in $Values) {
        $sumSquares += [Math]::Pow($value - $mean, 2)
    }
    $standardDeviation = [Math]::Sqrt($sumSquares / ($count - 1))
    $critical = Get-TCritical95 ($count - 1)
    $margin = $critical * $standardDeviation / [Math]::Sqrt($count)
    return [pscustomobject]@{
        sample_count = $count
        mean = $mean
        standard_deviation = $standardDeviation
        ci95_margin = $margin
        ci95_lower = $mean - $margin
        ci95_upper = $mean + $margin
    }
}

$plan = @(
    for ($repeat = 1; $repeat -le $Repeats; $repeat++) {
        foreach ($workerCount in $WorkerCounts) {
            [pscustomobject]@{
                repeat = $repeat
                worker_count = $workerCount
            }
        }
    }
)
$random = [System.Random]::new($RandomSeed)
for ($index = $plan.Count - 1; $index -gt 0; $index--) {
    $swapIndex = $random.Next($index + 1)
    $temporary = $plan[$index]
    $plan[$index] = $plan[$swapIndex]
    $plan[$swapIndex] = $temporary
}
$planWithOrder = @(
    for ($index = 0; $index -lt $plan.Count; $index++) {
        [pscustomobject]@{
            execution_order = $index + 1
            repeat = $plan[$index].repeat
            worker_count = $plan[$index].worker_count
        }
    }
)
$planWithOrder | Export-Csv `
    -NoTypeInformation `
    -Encoding UTF8 `
    (Join-Path $ArtifactRoot "randomized_run_plan.csv")

Push-Location $ProjectRoot
try {
    docker compose build | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "Compose image build failed"
    }

    foreach ($run in $planWithOrder) {
        docker compose down -v --remove-orphans | Out-Host
        docker compose up -d --scale worker=$($run.worker_count) | Out-Host
        if ($LASTEXITCODE -ne 0) {
            throw "Compose startup failed for worker_count=$($run.worker_count)"
        }

        $label = "order_$($run.execution_order)_repeat_$($run.repeat)_workers_$($run.worker_count)"
        & (Join-Path $PSScriptRoot "run_load_smoke.ps1") `
            -Users $Users `
            -SpawnRate $SpawnRate `
            -RunTime $RunTime `
            -WorkerCount $run.worker_count `
            -TaskType $TaskType `
            -SleepMs $SleepMs `
            -TopK $TopK `
            -RequestsPerUser $RequestsPerUser `
            -SampleIntervalMilliseconds $SampleIntervalMilliseconds `
            -ResourceSampleIntervalMilliseconds $ResourceSampleIntervalMilliseconds `
            -ArtifactRootName $ArtifactRootName `
            -Label $label
        if ($LASTEXITCODE -ne 0) {
            throw "Load run failed for $label"
        }

        $runDirectory = Join-Path $ArtifactRoot $label
        $summary = Get-Content `
            -Raw `
            -Encoding UTF8 `
            (Join-Path $runDirectory "run_summary.json") | ConvertFrom-Json
        $csvStats = Import-Csv (Join-Path $runDirectory "locust_stats.csv") |
            Where-Object { $_.Type -eq "POST" } |
            Select-Object -First 1
        $finalStats = Get-Content `
            -Raw `
            -Encoding UTF8 `
            (Join-Path $runDirectory "locust_final.json") | ConvertFrom-Json |
            Where-Object { $_.method -eq "POST" -and $_.name -eq "POST /tasks" } |
            Select-Object -First 1

        $rows += [pscustomobject]@{
            execution_order = $run.execution_order
            repeat = $run.repeat
            worker_count = $run.worker_count
            task_type = $summary.task_type
            run_id = $summary.run_id
            task_count = $summary.metrics.task_count
            api_requests_per_second = [double]$csvStats.'Requests/s'
            api_p95_ms = Get-WeightedPercentile $finalStats.response_times 0.95
            api_p99_ms = Get-WeightedPercentile $finalStats.response_times 0.99
            api_failure_count = [int]$finalStats.num_failures
            p95_queue_wait_ms = [double]$summary.metrics.p95_queue_wait_ms
            p99_queue_wait_ms = [double]$summary.metrics.p99_queue_wait_ms
            p95_runtime_ms = [double]$summary.metrics.p95_runtime_ms
            task_processing_utilization = [double]$summary.task_processing_utilization
            peak_broker_queue_length = [double]$summary.peak_broker_queue_length
            average_worker_cpu_percent_sum = [double]$summary.average_worker_cpu_percent_sum
            peak_worker_cpu_percent_sum = [double]$summary.peak_worker_cpu_percent_sum
            peak_worker_memory_mib_sum = [double]$summary.peak_worker_memory_mib_sum
            time_series_sample_count = [int]$summary.time_series_sample_count
        }
    }
}
finally {
    docker compose down -v --remove-orphans | Out-Host
    Pop-Location
}

$rawPath = Join-Path $ArtifactRoot "repeated_run_results.csv"
$rows | Sort-Object execution_order | Export-Csv -NoTypeInformation -Encoding UTF8 $rawPath

$metricNames = @(
    "api_requests_per_second",
    "api_p95_ms",
    "api_p99_ms",
    "p95_queue_wait_ms",
    "p99_queue_wait_ms",
    "p95_runtime_ms",
    "task_processing_utilization",
    "peak_broker_queue_length",
    "average_worker_cpu_percent_sum",
    "peak_worker_cpu_percent_sum",
    "peak_worker_memory_mib_sum"
)
$confidenceRows = @()
foreach ($workerCount in $WorkerCounts | Sort-Object) {
    $group = @($rows | Where-Object { $_.worker_count -eq $workerCount })
    foreach ($metricName in $metricNames) {
        $values = [double[]]@($group | ForEach-Object { [double]$_.$metricName })
        $statistics = Get-ConfidenceSummary $values
        $confidenceRows += [pscustomobject]@{
            worker_count = $workerCount
            metric = $metricName
            sample_count = $statistics.sample_count
            mean = $statistics.mean
            standard_deviation = $statistics.standard_deviation
            ci95_margin = $statistics.ci95_margin
            ci95_lower = $statistics.ci95_lower
            ci95_upper = $statistics.ci95_upper
        }
    }
}
$confidencePath = Join-Path $ArtifactRoot "worker_scaling_confidence_intervals.csv"
$confidenceRows | Export-Csv -NoTypeInformation -Encoding UTF8 $confidencePath

$metadata = [ordered]@{
    status = "single-machine local reference; not a capacity benchmark"
    generated_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    random_seed = $RandomSeed
    repeats = $Repeats
    worker_counts = $WorkerCounts
    users = $Users
    spawn_rate = $SpawnRate
    run_time = $RunTime
    task_type = $TaskType
    sleep_ms = $SleepMs
    top_k = $TopK
    requests_per_user = $RequestsPerUser
    sample_interval_ms = $SampleIntervalMilliseconds
    resource_sample_interval_ms = $ResourceSampleIntervalMilliseconds
    confidence_interval = "two-sided 95% Student t interval over independent local runs"
}
$metadata | ConvertTo-Json -Depth 5 | Set-Content `
    -Encoding UTF8 `
    (Join-Path $ArtifactRoot "experiment_metadata.json")

$rows | Sort-Object worker_count, repeat | Format-Table -AutoSize
$confidenceRows |
    Where-Object { $_.metric -in @("p95_queue_wait_ms", "task_processing_utilization") } |
    Format-Table -AutoSize
