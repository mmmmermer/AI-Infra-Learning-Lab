# E09 kind Reference

Status: `executable / verified local reference / learner pending`.

This directory deploys the P03 v0.3.1 multi-service path to a disposable kind
cluster:

```text
P03 API -> PostgreSQL task + outbox
       -> dispatcher -> Redis task_id queue
       -> 1/2/4 worker Deployment replicas
```

## Pinned Environment

- kind: v0.32.0.
- kind Windows binary SHA256:
  `0bcb2d1cfedc1912d664014db716937e8a0e843e91c6807b4db2025dbc8989fa`.
- Kubernetes node: v1.34.8.
- node image:
  `kindest/node:v1.34.8@sha256:02722c2dedddcfc00febf5d27fbeb9b7b2c14294c82109ff4a85d89ac9ba3256`.
- P03 image: `p03-service:0.3.1` loaded directly into the kind node.

## Run

```powershell
.\scripts\install_kind.ps1
.\scripts\verify_kind.ps1
```

`verify_kind.ps1` uses a dedicated kubeconfig under the ignored `.tools/`
directory. By default it deletes the `p03-lab` cluster after verification. Use
`-KeepCluster` only when you need to inspect the live objects manually.

## Verified Behavior

The 2026-07-11 local reference verified:

- kind cluster creation and Ready node.
- PostgreSQL, Redis, API, dispatcher, and worker Deployment rollout.
- P03 API running as numeric non-root UID 10001.
- public RAG denial and authorized private-source retrieval.
- task query after an API Deployment rollout.
- worker Deployment scaling to 1, 2, and 4 Ready replicas.
- 24 successful tasks and zero failures for every replica group.
- 1, 2, and 4 distinct persisted worker IDs for the 1/2/4 replica groups.

Observed queue waits from this single functional scaling run:

| Worker replicas | Tasks | Failures | Distinct worker IDs | Queue P95 | Queue P99 |
|---:|---:|---:|---:|---:|---:|
| 1 | 24 | 0 | 1 | 5608.94 ms | 5754.54 ms |
| 2 | 24 | 0 | 2 | 2055.22 ms | 2104.46 ms |
| 4 | 24 | 0 | 4 | 805.13 ms | 835.58 ms |

These timings are one functional kind run, not a benchmark or research result.
The machine, startup timing, and Kubernetes overhead differ from the repeated
Compose reference.

## Artifacts

- `artifacts/e09_kind_verification.json`: structured verification result.
- `artifacts/port-forward.*.log`: final port-forward logs.

## Boundaries

- PostgreSQL and Redis use `emptyDir`; dependency Pod replacement loses data.
- The Secret contains development-only local credentials committed for teaching.
- No Ingress, TLS, NetworkPolicy, PodDisruptionBudget, backup, external database,
  metrics-server, HPA, KEDA, Kueue, or production secret manager is installed.
- Scaling is manual and functional. It does not establish Kubernetes capacity.
- Reference verification does not count as learner reproduction.
