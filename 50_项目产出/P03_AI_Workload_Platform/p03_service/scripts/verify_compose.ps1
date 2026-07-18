[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$BaseUrl = "http://127.0.0.1:8001"
$OpsHeaders = @{ Authorization = "Bearer reference-ops-token" }
$PublicHeaders = @{ Authorization = "Bearer reference-public-token" }
$ComplianceHeaders = @{ Authorization = "Bearer reference-compliance-token" }

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
    throw "API did not become ready within 60 seconds"
}

function Submit-Task {
    param(
        [Parameter(Mandatory)] [string] $Key,
        [hashtable] $InputJson = @{},
        [string] $TaskType = "mock_rag",
        [hashtable] $Headers = $OpsHeaders
    )
    $body = @{
        task_type = $TaskType
        priority = 5
        estimated_duration_ms = 10
        idempotency_key = $Key
        input_json = $InputJson
    } | ConvertTo-Json -Depth 8
    return Invoke-RestMethod "$BaseUrl/tasks" `
        -Method Post `
        -ContentType "application/json" `
        -Headers $Headers `
        -Body $body
}

function Wait-TaskStatus {
    param(
        [Parameter(Mandatory)] [string] $TaskId,
        [Parameter(Mandatory)] [string[]] $Expected,
        [int] $TimeoutSeconds = 60,
        [hashtable] $Headers = $OpsHeaders
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $task = Invoke-RestMethod "$BaseUrl/tasks/$TaskId" -Headers $Headers
        if ($task.status -in $Expected) {
            return $task
        }
        Start-Sleep -Milliseconds 250
    }
    throw "Task $TaskId did not reach [$($Expected -join ', ')] within $TimeoutSeconds seconds"
}

Wait-Ready
$runId = [guid]::NewGuid().ToString("N")

$success = Submit-Task -Key "compose-success-$runId" -InputJson @{ query = "what is rag" }
$same = Submit-Task -Key "compose-success-$runId" -InputJson @{ query = "ignored duplicate" }
if (-not $success.created_new -or $same.created_new) {
    throw "Idempotency flags are incorrect"
}
if ($success.task.task_id -ne $same.task.task_id) {
    throw "Idempotent requests returned different task ids"
}
$completed = Wait-TaskStatus -TaskId $success.task.task_id -Expected @("succeeded")
if ($completed.result_json.kind -ne "mock_reference") {
    throw "Successful task did not persist its result"
}

$failure = Submit-Task -Key "compose-failure-$runId" -InputJson @{ force_error = $true }
$failed = Wait-TaskStatus -TaskId $failure.task.task_id -Expected @("failed")
if ($failed.error_type -ne "forced_failure") {
    throw "Deterministic failure was not persisted"
}

docker compose stop dispatcher | Out-Host
$backlog = Submit-Task -Key "compose-backlog-$runId" -InputJson @{ query = "outbox survives" }
Start-Sleep -Seconds 1
$pending = Invoke-RestMethod "$BaseUrl/tasks/$($backlog.task.task_id)" -Headers $OpsHeaders
if ($pending.status -ne "pending") {
    throw "Task should remain pending while dispatcher is stopped"
}
docker compose start dispatcher | Out-Host
$null = Wait-TaskStatus -TaskId $backlog.task.task_id -Expected @("succeeded")

$lease = Submit-Task -Key "compose-lease-$runId" -InputJson @{ sleep_ms = 5000 }
$null = Wait-TaskStatus -TaskId $lease.task.task_id -Expected @("running")
docker compose stop worker | Out-Host
Start-Sleep -Seconds 10
docker compose start worker | Out-Host
$null = Wait-TaskStatus -TaskId $lease.task.task_id -Expected @("succeeded") -TimeoutSeconds 30
$leaseCounts = docker compose exec -T db psql -U p03 -d p03 -tAc "SELECT retry_count || ':' || delivery_count FROM tasks WHERE task_id = '$($lease.task.task_id)';"
if ($leaseCounts.Trim() -ne "1:2") {
    throw "Lease recovery counters are incorrect: $leaseCounts"
}

docker compose restart api | Out-Host
Wait-Ready
$persisted = Invoke-RestMethod "$BaseUrl/tasks/$($success.task.task_id)" -Headers $OpsHeaders
if ($persisted.status -ne "succeeded") {
    throw "Task was not queryable after API restart"
}

$deliveryBefore = docker compose exec -T db psql -U p03 -d p03 -tAc "SELECT delivery_count FROM tasks WHERE task_id = '$($success.task.task_id)';"
docker compose exec -T redis redis-cli XADD p03:tasks:stream:v1 "*" task_id $success.task.task_id | Out-Host
Start-Sleep -Seconds 1
$deliveryAfter = docker compose exec -T db psql -U p03 -d p03 -tAc "SELECT delivery_count FROM tasks WHERE task_id = '$($success.task.task_id)';"
if ($deliveryBefore.Trim() -ne $deliveryAfter.Trim()) {
    throw "Duplicate Redis delivery executed the task again"
}

# Simulate a consumer crash after XREADGROUP reserve but before database claim.
docker compose stop worker | Out-Host
$reserveCrash = Submit-Task `
    -Key "compose-reserve-crash-$runId" `
    -InputJson @{ query = "pending stream delivery survives" }
$null = Wait-TaskStatus `
    -TaskId $reserveCrash.task.task_id `
    -Expected @("queued")
Start-Sleep -Seconds 1
$reserved = docker compose exec -T redis redis-cli --raw XREADGROUP `
    GROUP p03-workers crash-consumer COUNT 1 STREAMS p03:tasks:stream:v1 ">"
if (($reserved -join "`n") -notmatch [regex]::Escape($reserveCrash.task.task_id)) {
    throw "Crash consumer did not reserve the expected stream message"
}
docker compose start worker | Out-Host
$null = Wait-TaskStatus `
    -TaskId $reserveCrash.task.task_id `
    -Expected @("succeeded") `
    -TimeoutSeconds 30

$publicRag = Submit-Task `
    -Key "compose-rag-public-$runId" `
    -TaskType "rag_retrieval" `
    -Headers $PublicHeaders `
    -InputJson @{ query = "客户 ZETA 为什么需要额外人工复核？"; top_k = 5 }
$publicRagDone = Wait-TaskStatus `
    -TaskId $publicRag.task.task_id `
    -Expected @("succeeded") `
    -Headers $PublicHeaders
if ($publicRagDone.result_json.sources.permission_group -contains "compliance_private") {
    throw "Public RAG task leaked a private source"
}
if (
    $publicRagDone.result_json.retrieval_status -ne "no_relevant_authorized_source" -or
    $publicRagDone.result_json.sources.Count -ne 0
) {
    throw "Public RAG task should return an explicit no-relevant-source result"
}

$privateRag = Submit-Task `
    -Key "compose-rag-private-$runId" `
    -TaskType "rag_retrieval" `
    -Headers $ComplianceHeaders `
    -InputJson @{ query = "客户 ZETA 为什么需要额外人工复核？"; top_k = 3 }
$privateRagDone = Wait-TaskStatus `
    -TaskId $privateRag.task.task_id `
    -Expected @("succeeded") `
    -Headers $ComplianceHeaders
if ($privateRagDone.result_json.sources[0].document_id -ne "doc_compliance_private_001") {
    throw "Authorized RAG task did not retrieve the private source first"
}
if ($privateRagDone.result_json.retrieval_status -ne "ok") {
    throw "Authorized RAG task did not report a successful retrieval status"
}

$ownerIsolation = $false
try {
    Invoke-RestMethod "$BaseUrl/tasks/$($privateRag.task.task_id)" -Headers $PublicHeaders
}
catch {
    if ($_.Exception.Response.StatusCode -eq 404) {
        $ownerIsolation = $true
    }
}
if (-not $ownerIsolation) {
    throw "Task ownership boundary did not hide another user's task"
}

$metrics = Invoke-RestMethod "$BaseUrl/metrics" -Headers $OpsHeaders
if ($metrics.status_counts.succeeded -lt 3 -or $metrics.status_counts.failed -lt 1) {
    throw "Metrics do not reflect completed integration tasks"
}

[pscustomobject]@{
    ready = $true
    idempotency = $true
    success_path = $true
    failure_path = $true
    outbox_backlog_recovery = $true
    worker_lease_recovery = $true
    api_restart_persistence = $true
    duplicate_delivery_ignored = $true
    reserve_before_claim_recovered = $true
    rag_permission_prefilter = $true
    task_owner_isolation = $true
    task_count = $metrics.task_count
} | Format-List
