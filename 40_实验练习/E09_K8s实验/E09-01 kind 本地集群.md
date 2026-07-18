# E09-01 kind 本地集群

> 状态（2026-07-18）：`内容 content-reviewed / 实现 executable / Reference verified / 教学 partial / 归属 reference / 学习者 pending`。kind v0.32.0 已按官方 SHA256 校验安装；固定 Kubernetes v1.34.8 node image 后，集群创建、Ready Node、P03 多服务部署和完整清理均已实跑。

## 实验目的

创建一个一次性本地 Kubernetes 集群，确认 Node、Pod、事件和清理命令可用。这个实验只建立 E09 的运行底座，不部署数据库，也不把“kubectl 已安装”当成“集群已存在”。

## 前置检查

```powershell
docker version
kubectl version --client -o yaml
kind version
```

通过条件：

- Docker client 和 server 都能返回版本。
- `kubectl` 客户端可执行。
- `kind version` 成功。

安装 `kind` 前应从 [kind 官方 Quick Start](https://kind.sigs.k8s.io/docs/user/quick-start/) 选择 Windows 安装方式并记录版本与校验信息，不在学习库中静默下载未知二进制文件。

## 集群配置

创建 `kind-e09.yaml`：

```yaml
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
  - role: control-plane
```

单节点足够验证 Deployment、Service 和 port-forward。多节点、Ingress controller 和存储插件不属于 E09-01。

## 创建与检查

```powershell
kind create cluster --config kind-e09.yaml --wait 120s
kind get clusters
kubectl config current-context
kubectl cluster-info --context kind-p03-lab
kubectl get nodes -o wide
kubectl get pods -A
```

实际 reference 使用 `--name p03-lab` 传入集群名，并固定：

```text
kind v0.32.0
kind SHA256: 0bcb2d1cfedc1912d664014db716937e8a0e843e91c6807b4db2025dbc8989fa
node: kindest/node:v1.34.8@sha256:02722c2dedddcfc00febf5d27fbeb9b7b2c14294c82109ff4a85d89ac9ba3256
```

可执行入口为 `kind_reference/scripts/install_kind.ps1` 和
`kind_reference/scripts/verify_kind.ps1`。

必须确认当前 context 是 `kind-p03-lab`，避免误操作其他 Kubernetes 集群。

## 最小 Pod 验证

```powershell
kubectl create deployment hello --image=nginx:1.27-alpine
kubectl rollout status deployment/hello --timeout=120s
kubectl get pods -o wide
kubectl describe deployment hello
kubectl get events --sort-by=.metadata.creationTimestamp
kubectl delete deployment hello
```

这里的 `nginx` 只验证调度和镜像拉取，不代表 P03 已部署。

## 清理

```powershell
kind delete cluster --name p03-lab
kind get clusters
kubectl config get-contexts
```

删除后应确认 `p03-lab` 不再出现在 `kind get clusters` 中。不要只关闭终端而保留未知状态的实验集群。

## 诊断表

| 现象 | 检查 | 处理 |
|---|---|---|
| Docker API 不可用 | `docker info` | 启动 Docker Desktop Linux engine |
| `kind` 找不到 | `Get-Command kind` | 按官方文档安装并记录版本 |
| Node 一直 NotReady | `kubectl describe node`、`kubectl get pods -A` | 检查 CNI、镜像和 Docker 资源 |
| Pod ImagePullBackOff | `kubectl describe pod` | 检查镜像名、网络或本地镜像加载 |
| context 错误 | `kubectl config current-context` | 显式使用 `--context kind-p03-lab` |

## 记录字段

```text
run_date
docker_client_version
docker_server_version
kubectl_client_version
kind_version
node_image
context
node_status
pod_status
cleanup_result
error_type
fix_notes
```

## 学习者验收

Reference 已验证上面的安装、创建、Ready、部署和删除路径；下面勾选仍只记录
学习者本人复现。

- [ ] 安装来源、版本和校验信息可追溯。
- [ ] 能创建 `p03-lab` 并看到 Ready Node。
- [ ] 能部署、观察和删除一个测试 Deployment。
- [ ] 能用 events/describe 解释至少一个失败。
- [ ] 能完整删除集群并确认 context 状态。

## 边界

本实验不验证 P03、不安装 Kueue、不启用 HPA、不部署 Ingress，也不把 Docker Desktop 自带环境当成独立学习者 Linux/WSL 发行版。
