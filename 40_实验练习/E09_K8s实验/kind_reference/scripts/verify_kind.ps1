[CmdletBinding()]
param(
    [switch] $KeepCluster
)

$ErrorActionPreference = "Stop"
$ReferenceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$RepositoryRoot = (Resolve-Path (Join-Path $ReferenceRoot "..\..\..")).Path
$P03ProjectRoot = Get-ChildItem `
    -LiteralPath $RepositoryRoot `
    -Directory `
    -Recurse `
    -Filter "P03_AI_Workload_Platform" |
    Select-Object -First 1
if ($null -eq $P03ProjectRoot) {
    throw "P03_AI_Workload_Platform directory was not found"
}
$P03Root = Join-Path $P03ProjectRoot.FullName "p03_service"
$KindPath = Join-Path $RepositoryRoot ".tools\kind\v0.32.0\kind.exe"
$KubeconfigPath = Join-Path $RepositoryRoot ".tools\kind\kubeconfigs\p03-lab.yaml"
$ArtifactDirectory = Join-Path $ReferenceRoot "artifacts"
$ResultPath = Join-Path $ArtifactDirectory "e09_kind_verification.json"
$ClusterName = "p03-lab"
$Namespace = "p03-lab"
$NodeImage = "kindest/node:v1.34.8@sha256:02722c2dedddcfc00febf5d27fbeb9b7b2c14294c82109ff4a85d89ac9ba3256"
$BaseUrl = "http://127.0.0.1:18001"
$OpsHeaders = @{ Authorization = "Bearer reference-ops-token" }
$PublicHeaders = @{ Authorization = "Bearer reference-public-token" }
$ComplianceHeaders = @{ Authorization = "Bearer reference-compliance-token" }
$PortForwardProcess = $null
$ClusterCreated = $false

New-Item -ItemType Directory -Force (Split-Path $KubeconfigPath) | Out-Null
New-Item -ItemType Directory -Force $ArtifactDirectory | Out-Null

if (-not (Test-Path -LiteralPath $KindPath)) {
    & (Join-Path $PSScriptRoot "install_kind.ps1")
}

function Invoke-Kubectl {
    param([Parameter(Mandatory)] [string[]] $Arguments)
    $output = & kubectl --kubeconfig $KubeconfigPath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "kubectl failed: $($Arguments -join ' ')"
    }
    return $output
}

function Wait-ApiReady {
    $deadline = (Get-Date).AddSeconds(90)
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
    throw "P03 API did not become ready through Kubernetes port-forward"
}

function Stop-ApiPortForward {
    if (
        $null -ne $script:PortForwardProcess -and
        -not $script:PortForwardProcess.HasExited
    ) {
        Stop-Process `
            -Id $script:PortForwardProcess.Id `
            -Force `
            -ErrorAction SilentlyContinue
    }
    $script:PortForwardProcess = $null
}

function Start-ApiPortForward {
    Stop-ApiPortForward
    $kubectlPath = (Get-Command kubectl).Source
    $script:PortForwardProcess = Start-Process `
        -FilePath $kubectlPath `
        -ArgumentList @(
            "--kubeconfig", $KubeconfigPath,
            "-n", $Namespace,
            "port-forward", "service/p03-api", "18001:8000"
        ) `
        -PassThru `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $ArtifactDirectory "port-forward.stdout.log") `
        -RedirectStandardError (Join-Path $ArtifactDirectory "port-forward.stderr.log")
    Wait-ApiReady
}

function Submit-Task {
    param(
        [Parameter(Mandatory)] [string] $Key,
        [Parameter(Mandatory)] [string] $TaskType,
        [Parameter(Mandatory)] [hashtable] $InputJson,
        [Parameter(Mandatory)] [hashtable] $Headers
    )
    $body = @{
        task_type = $TaskType
        priority = 5
        estimated_duration_ms = if ($InputJson.ContainsKey("sleep_ms")) {
            [int]$InputJson.sleep_ms
        } else { 0 }
        idempotency_key = $Key
        input_json = $InputJson
    } | ConvertTo-Json -Depth 8
    return Invoke-RestMethod `
        "$BaseUrl/tasks" `
        -Method Post `
        -ContentType "application/json" `
        -Headers $Headers `
        -Body $body
}

function Wait-Task {
    param(
        [Parameter(Mandatory)] [string] $TaskId,
        [Parameter(Mandatory)] [hashtable] $Headers,
        [int] $TimeoutSeconds = 90
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $task = Invoke-RestMethod "$BaseUrl/tasks/$TaskId" -Headers $Headers
        if ($task.status -in @("succeeded", "failed")) {
            return $task
        }
        Start-Sleep -Milliseconds 250
    }
    throw "Task $TaskId did not reach a terminal state"
}

function Invoke-WorkerReplicaCase {
    param([Parameter(Mandatory)] [int] $ReplicaCount)
    Invoke-Kubectl @("-n", $Namespace, "scale", "deployment/p03-worker", "--replicas=$ReplicaCount") | Out-Host
    Invoke-Kubectl @(
        "-n", $Namespace, "rollout", "status", "deployment/p03-worker", "--timeout=120s"
    ) | Out-Host

    $readyReplicas = [int](
        Invoke-Kubectl @(
            "-n", $Namespace, "get", "deployment/p03-worker",
            "-o", "jsonpath={.status.readyReplicas}"
        )
    )
    if ($readyReplicas -ne $ReplicaCount) {
        throw "Expected $ReplicaCount ready workers, got $readyReplicas"
    }

    $runId = "e09-workers-$ReplicaCount-$([guid]::NewGuid().ToString('N'))"
    $submitted = 24
    for ($index = 1; $index -le $submitted; $index++) {
        $null = Submit-Task `
            -Key "$runId-$index" `
            -TaskType "mock_rag" `
            -Headers $OpsHeaders `
            -InputJson @{ run_id = $runId; sleep_ms = 200; order = $index }
    }

    $deadline = (Get-Date).AddSeconds(120)
    do {
        $metrics = Invoke-RestMethod "$BaseUrl/metrics?run_id=$runId" -Headers $OpsHeaders
        $unfinished =
            $metrics.status_counts.pending +
            $metrics.status_counts.queued +
            $metrics.status_counts.running +
            $metrics.status_counts.retrying
        if (
            $metrics.task_count -eq $submitted -and
            $unfinished -eq 0 -and
            $metrics.pending_outbox_count -eq 0
        ) {
            break
        }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)
    if ($metrics.task_count -ne $submitted -or $unfinished -ne 0) {
        throw "Replica case $ReplicaCount did not drain all tasks"
    }

    $workerCountOutput = Invoke-Kubectl @(
        "-n", $Namespace, "exec", "deployment/p03-db", "--",
        "psql", "-U", "p03", "-d", "p03", "-tAc",
        "SELECT COUNT(DISTINCT worker_id) FROM tasks WHERE input_json->>'run_id' = '$runId';"
    )
    $distinctWorkers = [int]($workerCountOutput.Trim())
    if ($distinctWorkers -lt [Math]::Min($ReplicaCount, 2)) {
        throw "Replica case $ReplicaCount used only $distinctWorkers distinct worker(s)"
    }

    return [pscustomobject]@{
        replicas = $ReplicaCount
        ready_replicas = $readyReplicas
        submitted_tasks = $submitted
        succeeded_tasks = $metrics.status_counts.succeeded
        failed_tasks = $metrics.status_counts.failed
        distinct_worker_ids = $distinctWorkers
        p95_queue_wait_ms = $metrics.p95_queue_wait_ms
        p99_queue_wait_ms = $metrics.p99_queue_wait_ms
    }
}

try {
    $existingClusters = @(& $KindPath get clusters)
    if ($existingClusters -contains $ClusterName) {
        & $KindPath delete cluster --name $ClusterName
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to delete pre-existing kind cluster $ClusterName"
        }
    }

    Push-Location $P03Root
    try {
        docker compose build api | Out-Host
        if ($LASTEXITCODE -ne 0) {
            throw "P03 image build failed"
        }
    }
    finally {
        Pop-Location
    }

    & $KindPath create cluster `
        --name $ClusterName `
        --image $NodeImage `
        --config (Join-Path $ReferenceRoot "kind-e09.yaml") `
        --kubeconfig $KubeconfigPath `
        --wait 180s
    if ($LASTEXITCODE -ne 0) {
        throw "kind cluster creation failed"
    }
    $ClusterCreated = $true

    Invoke-Kubectl @("wait", "--for=condition=Ready", "node", "--all", "--timeout=120s") | Out-Host
    & $KindPath load docker-image p03-service:0.3.1 --name $ClusterName
    if ($LASTEXITCODE -ne 0) {
        throw "kind image load failed"
    }

    Invoke-Kubectl @("apply", "-k", (Join-Path $ReferenceRoot "manifests")) | Out-Host
    foreach ($deployment in @("p03-db", "p03-redis", "p03-api", "p03-dispatcher", "p03-worker")) {
        Invoke-Kubectl @(
            "-n", $Namespace, "rollout", "status", "deployment/$deployment", "--timeout=180s"
        ) | Out-Host
    }

    Start-ApiPortForward

    $runToken = [guid]::NewGuid().ToString("N")
    $public = Submit-Task `
        -Key "e09-public-$runToken" `
        -TaskType "rag_retrieval" `
        -Headers $PublicHeaders `
        -InputJson @{ query = "客户 ZETA 为什么需要额外人工复核？"; top_k = 5 }
    $publicDone = Wait-Task -TaskId $public.task.task_id -Headers $PublicHeaders
    if (
        $publicDone.result_json.retrieval_status -ne "no_relevant_authorized_source" -or
        $publicDone.result_json.sources.Count -ne 0
    ) {
        throw "Public Kubernetes RAG task crossed the permission boundary"
    }

    $private = Submit-Task `
        -Key "e09-private-$runToken" `
        -TaskType "rag_retrieval" `
        -Headers $ComplianceHeaders `
        -InputJson @{ query = "客户 ZETA 为什么需要额外人工复核？"; top_k = 3 }
    $privateDone = Wait-Task -TaskId $private.task.task_id -Headers $ComplianceHeaders
    if ($privateDone.result_json.sources[0].document_id -ne "doc_compliance_private_001") {
        throw "Authorized Kubernetes RAG task missed its private source"
    }

    $replicaResults = @(
        Invoke-WorkerReplicaCase 1
        Invoke-WorkerReplicaCase 2
        Invoke-WorkerReplicaCase 4
    )

    Invoke-Kubectl @("-n", $Namespace, "rollout", "restart", "deployment/p03-api") | Out-Host
    Invoke-Kubectl @(
        "-n", $Namespace, "rollout", "status", "deployment/p03-api", "--timeout=120s"
    ) | Out-Host
    Start-ApiPortForward
    $persisted = Invoke-RestMethod "$BaseUrl/tasks/$($private.task.task_id)" -Headers $ComplianceHeaders
    if ($persisted.status -ne "succeeded") {
        throw "Task did not remain queryable after Kubernetes API rollout"
    }

    $apiUserId = (
        Invoke-Kubectl @("-n", $Namespace, "exec", "deployment/p03-api", "--", "id", "-u")
    ).Trim()
    if ($apiUserId -eq "0") {
        throw "P03 API is running as root in Kubernetes"
    }

    $nodeVersion = Invoke-Kubectl @("get", "node", "-o", "jsonpath={.items[0].status.nodeInfo.kubeletVersion}")
    $result = [ordered]@{
        status = "verified local kind reference; learner pending"
        verified_at_utc = (Get-Date).ToUniversalTime().ToString("o")
        kind_version = (& $KindPath version).Trim()
        node_image = $NodeImage
        kubelet_version = $nodeVersion
        namespace = $Namespace
        api_non_root_uid = $apiUserId
        rag_permission_prefilter = $true
        api_rollout_persistence = $true
        replica_results = $replicaResults
        storage_boundary = "PostgreSQL and Redis use emptyDir; data is not durable across dependency pod replacement"
    }
    $result | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 $ResultPath
    $result | ConvertTo-Json -Depth 8
}
catch {
    if ($ClusterCreated) {
        try {
            Invoke-Kubectl @("-n", $Namespace, "get", "all", "-o", "wide") |
                Set-Content -Encoding UTF8 (Join-Path $ArtifactDirectory "failure-objects.log")
            Invoke-Kubectl @("-n", $Namespace, "get", "events", "--sort-by=.metadata.creationTimestamp") |
                Set-Content -Encoding UTF8 (Join-Path $ArtifactDirectory "failure-events.log")
        }
        catch {
            # Preserve the original verification failure.
        }
    }
    throw
}
finally {
    Stop-ApiPortForward
    if ($ClusterCreated -and -not $KeepCluster) {
        & $KindPath delete cluster --name $ClusterName
    }
}
