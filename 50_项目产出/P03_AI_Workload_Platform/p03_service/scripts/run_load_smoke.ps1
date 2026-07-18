[CmdletBinding()]
param(
    [int] $Users = 5,
    [int] $SpawnRate = 5,
    [string] $RunTime = "10s",
    [int] $WorkerCount = 1,
    [ValidateSet("mock_rag", "rag_retrieval")]
    [string] $TaskType = "mock_rag",
    [int] $SleepMs = 25,
    [int] $TopK = 3,
    [string] $Query = "RAG 回答为什么需要来源引用？",
    [double] $RequestsPerUser = 5,
    [string] $Label = "single_worker",
    [int] $SampleIntervalMilliseconds = 500,
    [int] $ResourceSampleIntervalMilliseconds = 2000,
    [string] $ArtifactRootName = "e08_reference_smoke"
)

$ErrorActionPreference = "Stop"
$BaseUrl = "http://127.0.0.1:8001"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"
$ArtifactDirectory = Join-Path $PSScriptRoot "..\artifacts\$ArtifactRootName\$Label"
$CsvPrefix = Join-Path $ArtifactDirectory "locust"
$JsonPrefix = Join-Path $ArtifactDirectory "locust_final"
$RunId = "e08-$Label-$([guid]::NewGuid().ToString('N'))"
$Headers = @{ Authorization = "Bearer reference-ops-token" }
$TimeSeriesPath = Join-Path $ArtifactDirectory "timeseries.csv"
$WorkerResourcesPath = Join-Path $ArtifactDirectory "worker_resources.csv"
$ResourceSamplingFlag = Join-Path $ArtifactDirectory ".resource-sampling-$RunId"
$LocustStdoutPath = Join-Path $ArtifactDirectory "locust_stdout.log"
$LocustStderrPath = Join-Path $ArtifactDirectory "locust_stderr.log"

if (-not (Test-Path $Python)) {
    throw "Create .venv and install requirements-dev.lock before running the load smoke"
}
New-Item -ItemType Directory -Force $ArtifactDirectory | Out-Null

function Wait-Ready {
    $deadline = (Get-Date).AddSeconds(60)
    while ((Get-Date) -lt $deadline) {
        try {
            $ready = Invoke-RestMethod "$BaseUrl/ready" -TimeoutSec 3
            if ($ready.status -eq "ready") {
                return
            }
        }
        catch {
            Start-Sleep -Milliseconds 500
        }
    }
    throw "P03 API did not become ready within 60 seconds"
}

Wait-Ready
$baseline = Invoke-RestMethod "$BaseUrl/metrics" -Headers $Headers
if ($baseline.task_count -ne 0) {
    throw "Load smoke requires an empty task store; recreate the Compose volumes before running"
}

$resourceJob = $null
$resourceRows = @()
try {
    $env:P03_LOAD_RUN_ID = $RunId
    $env:P03_LOAD_TASK_TYPE = $TaskType
    $env:P03_LOAD_SLEEP_MS = $SleepMs
    $env:P03_LOAD_TOP_K = $TopK
    $env:P03_LOAD_QUERY = $Query
    $env:P03_LOAD_REQUESTS_PER_USER = $RequestsPerUser
    $locustArguments = @(
        "-m", "locust",
        "-f", (Join-Path $PSScriptRoot "..\load\locustfile.py"),
        "--headless",
        "--users", "$Users",
        "--spawn-rate", "$SpawnRate",
        "--run-time", $RunTime,
        "--stop-timeout", "5",
        "--host", $BaseUrl,
        "--csv", $CsvPrefix,
        "--json-file", $JsonPrefix,
        "--only-summary"
    )
    $loadStartedAt = (Get-Date).ToUniversalTime()
    $processStartInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $processStartInfo.FileName = $Python
    $processStartInfo.Arguments = $locustArguments -join " "
    $processStartInfo.UseShellExecute = $false
    $processStartInfo.CreateNoWindow = $true
    $processStartInfo.RedirectStandardOutput = $true
    $processStartInfo.RedirectStandardError = $true
    $locustProcess = [System.Diagnostics.Process]::new()
    $locustProcess.StartInfo = $processStartInfo
    if (-not $locustProcess.Start()) {
        throw "Locust process did not start"
    }
    $stdoutTask = $locustProcess.StandardOutput.ReadToEndAsync()
    $stderrTask = $locustProcess.StandardError.ReadToEndAsync()

    Set-Content -Encoding ASCII $ResourceSamplingFlag "running"
    $resourceJob = Start-Job `
        -ArgumentList $ProjectRoot, $ResourceSamplingFlag, $ResourceSampleIntervalMilliseconds `
        -ScriptBlock {
            param($WorkingDirectory, $SamplingFlag, $SamplingIntervalMilliseconds)
            Set-Location $WorkingDirectory

            function Convert-ToMiB {
                param([Parameter(Mandatory)] [string] $Value)
                if ($Value -notmatch '^([0-9.]+)(B|KiB|MiB|GiB)$') {
                    return $null
                }
                $number = [double]$Matches[1]
                switch ($Matches[2]) {
                    "B" { return $number / 1MB }
                    "KiB" { return $number / 1024 }
                    "MiB" { return $number }
                    "GiB" { return $number * 1024 }
                }
            }

            while (Test-Path -LiteralPath $SamplingFlag) {
                $sampledAt = (Get-Date).ToUniversalTime()
                $workerIds = @(docker compose ps -q worker)
                $cpuValues = @()
                $memoryValues = @()
                if ($workerIds.Count) {
                    $stats = @(
                        docker stats `
                            --no-stream `
                            --format "{{.CPUPerc}}|{{.MemUsage}}" `
                            $workerIds
                    )
                    foreach ($line in $stats) {
                        $parts = $line -split '\|', 2
                        if ($parts.Count -ne 2) {
                            continue
                        }
                        $cpuValues += [double]($parts[0].Trim().TrimEnd('%'))
                        $usedMemory = ($parts[1] -split '/', 2)[0].Trim()
                        $memoryMiB = Convert-ToMiB $usedMemory
                        if ($null -ne $memoryMiB) {
                            $memoryValues += $memoryMiB
                        }
                    }
                }
                $cpuSum = ($cpuValues | Measure-Object -Sum).Sum
                $memorySum = ($memoryValues | Measure-Object -Sum).Sum
                [pscustomobject]@{
                    sampled_at_utc = $sampledAt.ToString("o")
                    worker_container_count = $workerIds.Count
                    worker_cpu_percent_sum = if ($cpuValues.Count) {
                        [double]$cpuSum
                    } else { $null }
                    worker_cpu_percent_mean = if ($cpuValues.Count) {
                        [double]$cpuSum / $cpuValues.Count
                    } else { $null }
                    worker_memory_mib_sum = if ($memoryValues.Count) {
                        [double]$memorySum
                    } else { $null }
                }
                Start-Sleep -Milliseconds $SamplingIntervalMilliseconds
            }
        }

    $timeSeries = @()
    while (-not $locustProcess.HasExited) {
        $sampledAt = (Get-Date).ToUniversalTime()
        $sampleMetrics = $null
        try {
            $sampleMetrics = Invoke-RestMethod `
                "$BaseUrl/metrics?run_id=$RunId" `
                -Headers $Headers `
                -TimeoutSec 3
        }
        catch {
            # A missing sample is retained explicitly rather than terminating the load.
        }
        $timeSeries += [pscustomobject]@{
            sampled_at_utc = $sampledAt.ToString("o")
            elapsed_ms = [math]::Round(
                ($sampledAt - $loadStartedAt).TotalMilliseconds,
                3
            )
            task_count = if ($null -ne $sampleMetrics) { $sampleMetrics.task_count } else { $null }
            broker_queue_length = if ($null -ne $sampleMetrics) {
                $sampleMetrics.broker_queue_length
            } else {
                $null
            }
            active_workers = if ($null -ne $sampleMetrics) {
                $sampleMetrics.active_workers
            } else {
                $null
            }
            pending_outbox_count = if ($null -ne $sampleMetrics) {
                $sampleMetrics.pending_outbox_count
            } else {
                $null
            }
            completed_last_minute = if ($null -ne $sampleMetrics) {
                $sampleMetrics.completed_last_minute
            } else {
                $null
            }
        }
        Start-Sleep -Milliseconds $SampleIntervalMilliseconds
        $locustProcess.Refresh()
    }
    $locustProcess.WaitForExit()
    Remove-Item -LiteralPath $ResourceSamplingFlag -ErrorAction SilentlyContinue
    $null = Wait-Job -Job $resourceJob -Timeout 15
    if ($resourceJob.State -ne "Completed") {
        Stop-Job -Job $resourceJob
    }
    $resourceRows = @(Receive-Job -Job $resourceJob)
    Remove-Job -Job $resourceJob -Force
    $resourceJob = $null
    $stdoutTask.Result | Set-Content -Encoding UTF8 $LocustStdoutPath
    $stderrTask.Result | Set-Content -Encoding UTF8 $LocustStderrPath
    $timeSeries | Export-Csv -NoTypeInformation -Encoding UTF8 $TimeSeriesPath
    $resourceRows |
        Select-Object `
            sampled_at_utc, `
            worker_container_count, `
            worker_cpu_percent_sum, `
            worker_cpu_percent_mean, `
            worker_memory_mib_sum |
        Export-Csv -NoTypeInformation -Encoding UTF8 $WorkerResourcesPath
    if ($locustProcess.ExitCode -ne 0) {
        throw "Locust smoke failed with exit code $($locustProcess.ExitCode); see $LocustStderrPath"
    }
}
finally {
    Remove-Item -LiteralPath $ResourceSamplingFlag -ErrorAction SilentlyContinue
    if ($null -ne $resourceJob) {
        Stop-Job -Job $resourceJob -ErrorAction SilentlyContinue
        Remove-Job -Job $resourceJob -Force -ErrorAction SilentlyContinue
    }
    Remove-Item Env:P03_LOAD_RUN_ID -ErrorAction SilentlyContinue
    Remove-Item Env:P03_LOAD_TASK_TYPE -ErrorAction SilentlyContinue
    Remove-Item Env:P03_LOAD_SLEEP_MS -ErrorAction SilentlyContinue
    Remove-Item Env:P03_LOAD_TOP_K -ErrorAction SilentlyContinue
    Remove-Item Env:P03_LOAD_QUERY -ErrorAction SilentlyContinue
    Remove-Item Env:P03_LOAD_REQUESTS_PER_USER -ErrorAction SilentlyContinue
}

$deadline = (Get-Date).AddSeconds(60)
do {
    $metrics = Invoke-RestMethod "$BaseUrl/metrics?run_id=$RunId" -Headers $Headers
    $unfinished =
        $metrics.status_counts.pending +
        $metrics.status_counts.queued +
        $metrics.status_counts.running +
        $metrics.status_counts.retrying
    if ($unfinished -eq 0 -and $metrics.pending_outbox_count -eq 0) {
        break
    }
    Start-Sleep -Milliseconds 500
} while ((Get-Date) -lt $deadline)

if ($unfinished -ne 0) {
    throw "Load stopped but $unfinished task(s) did not reach a terminal state"
}
$locustStats = Get-Content -Raw -Encoding UTF8 "$JsonPrefix.json" |
    ConvertFrom-Json |
    Where-Object { $_.method -eq "POST" -and $_.name -eq "POST /tasks" } |
    Select-Object -First 1
if ($null -eq $locustStats) {
    throw "Locust final JSON does not contain the POST /tasks row"
}
if ([int]$locustStats.num_requests -ne $metrics.task_count) {
    throw "Locust request count does not match run task count"
}

$metrics | ConvertTo-Json -Depth 6 | Set-Content `
    -Encoding UTF8 `
    (Join-Path $ArtifactDirectory "metrics_after_drain.json")

$utilization = $null
if ($metrics.observation_window_ms -gt 0 -and $WorkerCount -gt 0) {
    $utilization =
        $metrics.worker_busy_time_ms /
        ($WorkerCount * $metrics.observation_window_ms)
}
$timeSeriesRows = @(Import-Csv $TimeSeriesPath)
$resourceSeriesRows = @(Import-Csv $WorkerResourcesPath)
$queueSamples = @(
    $timeSeriesRows |
        Where-Object { $_.broker_queue_length -ne "" } |
        ForEach-Object { [double]$_.broker_queue_length }
)
$cpuSamples = @(
    $resourceSeriesRows |
        Where-Object { $_.worker_cpu_percent_sum -ne "" } |
        ForEach-Object { [double]$_.worker_cpu_percent_sum }
)
$memorySamples = @(
    $resourceSeriesRows |
        Where-Object { $_.worker_memory_mib_sum -ne "" } |
        ForEach-Object { [double]$_.worker_memory_mib_sum }
)
$summary = [ordered]@{
    run_id = $RunId
    label = $Label
    users = $Users
    spawn_rate = $SpawnRate
    run_time = $RunTime
    worker_count = $WorkerCount
    task_type = $TaskType
    sleep_ms = $SleepMs
    top_k = $TopK
    requests_per_user = $RequestsPerUser
    task_processing_utilization = $utilization
    sample_interval_ms = $SampleIntervalMilliseconds
    time_series_sample_count = $timeSeriesRows.Count
    resource_sample_interval_ms = $ResourceSampleIntervalMilliseconds
    resource_sample_count = $resourceSeriesRows.Count
    peak_broker_queue_length = if ($queueSamples.Count) {
        ($queueSamples | Measure-Object -Maximum).Maximum
    } else { $null }
    average_worker_cpu_percent_sum = if ($cpuSamples.Count) {
        ($cpuSamples | Measure-Object -Average).Average
    } else { $null }
    peak_worker_cpu_percent_sum = if ($cpuSamples.Count) {
        ($cpuSamples | Measure-Object -Maximum).Maximum
    } else { $null }
    peak_worker_memory_mib_sum = if ($memorySamples.Count) {
        ($memorySamples | Measure-Object -Maximum).Maximum
    } else { $null }
    metrics = $metrics
}
$summary | ConvertTo-Json -Depth 8 | Set-Content `
    -Encoding UTF8 `
    (Join-Path $ArtifactDirectory "run_summary.json")

[pscustomobject]@{
    run_id = $RunId
    users = $Users
    spawn_rate = $SpawnRate
    run_time = $RunTime
    worker_count = $WorkerCount
    task_type = $TaskType
    sleep_ms = $SleepMs
    top_k = $TopK
    requests_per_user = $RequestsPerUser
    task_count = $metrics.task_count
    failed_tasks = $metrics.status_counts.failed
    p95_queue_wait_ms = $metrics.p95_queue_wait_ms
    p99_queue_wait_ms = $metrics.p99_queue_wait_ms
    p95_runtime_ms = $metrics.p95_runtime_ms
    task_processing_utilization = $utilization
    peak_broker_queue_length = $summary.peak_broker_queue_length
    average_worker_cpu_percent_sum = $summary.average_worker_cpu_percent_sum
    peak_worker_memory_mib_sum = $summary.peak_worker_memory_mib_sum
    completed_last_minute = $metrics.completed_last_minute
    artifact_directory = $ArtifactDirectory
} | Format-List
