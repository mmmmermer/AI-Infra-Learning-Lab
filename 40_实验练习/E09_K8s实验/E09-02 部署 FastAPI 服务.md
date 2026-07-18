# E09-02 部署 FastAPI 服务

> 状态（2026-07-18）：`内容 content-reviewed / 实现 executable / Reference verified / 教学 partial / 归属 reference / 学习者 pending`。P03 v0.3.1 镜像已加载到 kind；PostgreSQL、Redis、API、dispatcher、worker 五类 Deployment 与三个 Service 均 rollout 成功。下方 memory manifest 仍保留为教学子集，完整 reference 在 `kind_reference/manifests/`。

## 实验目的

先理解如何把 `p03-service:0.3.1` 以显式 `memory` 模式部署为一个 Deployment 和 ClusterIP Service；可执行 reference 则使用 PostgreSQL 模式部署完整多服务路径，并通过 port-forward 验证 `/health`、`/ready` 和 Task API。

## 前置条件

- E09-01 的 `p03-lab` 集群处于 Ready。
- `p03-service:0.3.1` 已由 `p03_service/Dockerfile` 构建。
- 当前 context 明确为 `kind-p03-lab`。

```powershell
kubectl config current-context
docker image inspect p03-service:0.3.1
kind load docker-image p03-service:0.3.1 --name p03-lab
```

`kind load` 是本地镜像进入 kind Node 的关键步骤。若不加载，Pod 可能出现 `ImagePullBackOff`。

## 部署清单

保存为 `p03-api.yaml`：

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: p03-api
  labels:
    app.kubernetes.io/name: p03-api
spec:
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: p03-api
  template:
    metadata:
      labels:
        app.kubernetes.io/name: p03-api
    spec:
      containers:
        - name: api
          image: p03-service:0.3.1
          imagePullPolicy: IfNotPresent
          env:
            - name: P03_BACKEND
              value: memory
          ports:
            - name: http
              containerPort: 8000
          readinessProbe:
            httpGet:
              path: /ready
              port: http
            initialDelaySeconds: 2
            periodSeconds: 5
          livenessProbe:
            httpGet:
              path: /health
              port: http
            initialDelaySeconds: 10
            periodSeconds: 10
          resources:
            requests:
              cpu: 50m
              memory: 64Mi
            limits:
              cpu: 500m
              memory: 256Mi
          securityContext:
            runAsNonRoot: true
            allowPrivilegeEscalation: false
            capabilities:
              drop: ["ALL"]
---
apiVersion: v1
kind: Service
metadata:
  name: p03-api
spec:
  selector:
    app.kubernetes.io/name: p03-api
  ports:
    - name: http
      port: 8000
      targetPort: http
  type: ClusterIP
```

这里保留 `replicas: 1`，因为内联示例有意使用 `memory` 模式教学。P03 v0.3.1 的 PostgreSQL 模式可以共享任务，但必须连同 db、Redis、dispatcher 和 worker 一起迁移；`kind_reference/manifests/` 已按该边界实跑。

## 已验证完整 Reference

完整清单通过 Kustomize 部署到 `p03-lab` namespace，并验证：

- API `/ready` 同时检查 PostgreSQL 和 Redis。
- API Pod 以 UID/GID 10001 非 root 运行。
- public RAG 不返回 private source，compliance principal 可命中 private source。
- rollout restart API 后，已有 task 仍可从 PostgreSQL 查询。
- PostgreSQL/Redis 使用 `emptyDir`，不声称依赖 Pod 替换后的持久性。

## 部署与验证

```powershell
kubectl apply -f p03-api.yaml
kubectl rollout status deployment/p03-api --timeout=120s
kubectl get deployment,pod,service -l app.kubernetes.io/name=p03-api -o wide
kubectl port-forward service/p03-api 8001:8000
```

另开终端：

```powershell
Invoke-RestMethod http://127.0.0.1:8001/health
Invoke-RestMethod http://127.0.0.1:8001/ready
```

期望结果：

```json
{"status":"ok"}
```

## 进一步检查

```powershell
kubectl logs deployment/p03-api
kubectl describe deployment p03-api
kubectl get events --sort-by=.metadata.creationTimestamp
kubectl exec deployment/p03-api -- id
```

`id` 应显示非 root 用户。不要仅凭 YAML 中写了 `runAsNonRoot` 就假定镜像实际满足条件。

## 清理

```powershell
kubectl delete -f p03-api.yaml
kubectl get deployment,pod,service -l app.kubernetes.io/name=p03-api
```

## 学习者验收

- [ ] 本地镜像已加载到正确的 kind 集群。
- [ ] Deployment rollout 成功且 readiness 为 Ready。
- [ ] Service port-forward 能访问 `/health`。
- [ ] 容器以非 root 用户运行。
- [ ] 清理后无 P03 API 对象遗留。

## 边界

内联 manifest 只验证单 API Pod 基础；完整 reference 已验证 PostgreSQL/Redis/outbox/独立 worker 的 kind 迁移，但仍使用教学凭据和临时依赖存储，不是生产可扩展平台部署。
