param(
    [string]$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\.."))
)

$root = (Resolve-Path $RepositoryRoot).Path
$matrixPath = Join-Path $root "00_路线总控\审计与整改\01_逐文件整改矩阵.csv"

function New-MatrixRow {
    param([string]$RelativePath)

    $area = ($RelativePath -split "\\", 2)[0]
    [pscustomobject][ordered]@{
        file = $RelativePath
        area = $area
        review_state = "unreviewed"
        content_status = "unassessed"
        implementation_status = "unassessed"
        verification_status = "unassessed"
        ownership = "unassessed"
        instructional_readiness = "not-assessed"
        learner_validation = "not-evaluated"
        risk = "unknown"
        learning_blocker = "unknown"
        action = "人工复核"
        reason = "仅完成文件覆盖盘点，尚无逐文件人工成熟度结论"
        dependency = ""
        acceptance = "人工核对内容、实现、证据、教学就绪度与风险后再赋值"
    }
}

function Set-Classification {
    param(
        [object]$Row,
        [string]$Content,
        [string]$Implementation,
        [string]$Verification,
        [string]$Risk,
        [string]$Action,
        [string]$Reason,
        [string]$Dependency = "",
        [string]$Acceptance = "保持文档、代码、测试和状态一致"
    )

    $Row.review_state = "rule-reviewed"
    $Row.content_status = $Content
    $Row.implementation_status = $Implementation
    $Row.verification_status = $Verification
    $Row.ownership = "reference"
    $Row.instructional_readiness = "not-assessed"
    $Row.learner_validation = "not-evaluated"
    $Row.risk = $Risk
    $Row.learning_blocker = "否"
    $Row.action = $Action
    $Row.reason = $Reason
    $Row.dependency = $Dependency
    $Row.acceptance = $Acceptance
}

$includedExtensions = @(".md", ".py", ".sql", ".toml", ".yaml", ".yml", ".lock", ".ps1")
$includedNames = @(".gitignore", ".dockerignore", "Dockerfile")
$separatorPattern = [regex]::Escape([IO.Path]::DirectorySeparatorChar)
$excludedPattern = "$separatorPattern(\.git|\.obsidian|\.tools|\.venv|__pycache__|\.pytest_cache|[^$separatorPattern]+\.egg-info)($separatorPattern|$)"

$enumerationErrors = @()
$allFiles = Get-ChildItem -LiteralPath $root -Recurse -File `
    -ErrorAction SilentlyContinue -ErrorVariable +enumerationErrors
$unexpectedEnumerationErrors = @(
    $enumerationErrors | Where-Object {
        ([string]$_.TargetObject) -notmatch $excludedPattern
    }
)
if ($unexpectedEnumerationErrors.Count -gt 0) {
    throw "source enumeration failed outside excluded directories: $($unexpectedEnumerationErrors[0])"
}

$files = $allFiles | Where-Object {
    $_.FullName -notmatch $excludedPattern -and
    $_.FullName -ne $matrixPath -and
    ($includedExtensions -contains $_.Extension.ToLowerInvariant() -or $includedNames -contains $_.Name)
}

$rows = foreach ($file in $files) {
    $relative = $file.FullName.Substring($root.Length).TrimStart("\")
    $row = New-MatrixRow -RelativePath $relative

    if ($relative -in @(".gitignore", "README.md", "README_打开说明.md")) {
        Set-Classification $row "content-reviewed" "not-applicable" "verified" "low" "保留" "公开入口、发布边界和忽略规则已与现行验证证据对齐"
    } elseif (
        $relative -like "00_路线总控\看板与索引\00_*" -or
        $relative -like "00_路线总控\看板与索引\01_*" -or
        $relative -like "00_路线总控\看板与索引\08_*"
    ) {
        Set-Classification $row "content-reviewed" "not-applicable" "verified" "low" "保留" "现行入口、任务状态和多轴成熟度已与矩阵及统一门禁对齐"
    } elseif (
        $relative -like "10_学习模块\00_*" -or
        $relative -like "10_学习模块\*\*_学习地图.md"
    ) {
        Set-Classification $row "content-reviewed" "not-applicable" "verified" "low" "保留/随模块更新" "模块入口、先修、产物、版本和完成边界已规范化"
    } elseif ($relative -like "*\tools\validate_repository.py") {
        Set-Classification $row "content-reviewed" "executable" "verified" "low" "保留" "Markdown code fence and formal WikiLink validator passed"
    } elseif ($relative -like "*\tools\validate_encoding.py") {
        Set-Classification $row "content-reviewed" "executable" "verified" "low" "保留" "UTF-8、乱码字符、路径规范化和名称冲突门禁已通过"
    } elseif ($relative -like "*\tools\validate_file_matrix.py") {
        Set-Classification $row "content-reviewed" "executable" "verified" "low" "保留" "逐文件覆盖清单的列、状态、唯一路径、未知值约束和仓库覆盖门禁已通过"
    } elseif ($relative -like "*\tools\validate_structured_data.py") {
        Set-Classification $row "content-reviewed" "executable" "verified" "low" "保留" "JSON、TOML 和 CSV 结构解析门禁；CSV 禁止空记录和列宽漂移"
    } elseif ($relative -like "*\tools\validate_rq01_artifacts.py") {
        Set-Classification $row "content-reviewed" "executable" "verified" "low" "保留" "RQ01 发布文件 SHA-256、压缩快照安全路径、成员覆盖和逐文件哈希门禁"
    } elseif ($relative -like "*\tools\run_full_validation.ps1") {
        Set-Classification $row "content-reviewed" "executable" "verified" "low" "保留" "十套 Python 3.13 reference 共 399 项测试，逐项目期望数与总数由统一门禁校验，并覆盖编码、内容、Mermaid、编译和发布候选 diff"
    } elseif ($relative -like "*\tools\rebuild_remediation_matrix.ps1") {
        Set-Classification $row "content-reviewed" "executable" "verified" "low" "保留" "逐文件覆盖与自动分诊清单生成器已执行；未复核文件保持 unassessed/unknown"
    } elseif ($relative -like "*\tools\split_m05_textbook.ps1") {
        Set-Classification $row "content-reviewed" "executable" "verified" "low" "保留" "M05 7826 行源文件已按固定边界拆分，迁移 manifest 与哈希已生成"
    } elseif ($relative -like "*\tools\content_quality\*") {
        $implementation = if ($file.Extension -in @(".py", ".ps1")) { "executable" } else { "not-applicable" }
        Set-Classification $row "content-reviewed" $implementation "verified" "low" "保留" "固定版本开源内容质量检查器、配置和分析脚本已完成全库运行"
    } elseif ($relative -like "*\artifacts\content_quality_audit_2026-07-11\*") {
        Set-Classification $row "content-reviewed" "not-applicable" "verified" "low" "保留" "Markdown/Zhlint/Vale/Lychee 全库原始审计证据"
    } elseif ($relative -like "*\artifacts\official_docs_content_audit_2026-07-12\*") {
        Set-Classification $row "content-reviewed" "not-applicable" "verified" "low" "保留为历史快照" "2026-07-12 的 202 章历史 JSON/CSV；现行 210 章见 2026-07-18 artifact"
    } elseif ($relative -like "*\artifacts\m05_split_2026-07-11\*") {
        Set-Classification $row "content-reviewed" "not-applicable" "verified" "low" "保留" "M05 无损拆分的原始行区间、迁移瞬时哈希和使用说明"
    } elseif ($relative -like "*\artifacts\full_validation_2026-07-11\*") {
        Set-Classification $row "content-reviewed" "not-applicable" "verified" "low" "保留" "统一验证、编码门禁和修复前后对照证据"
    } elseif ($relative -like "*\05_教材内容质量大检查报告_2026-07-11.md") {
        Set-Classification $row "content-reviewed" "not-applicable" "verified" "low" "保留/按优先级整改" "开源工具交叉审计报告，已区分确认缺陷、风格建议和网络不确定项"
    } elseif ($relative -like "*\06_教材教学有效性与工具复核报告_2026-07-11.md") {
        Set-Classification $row "content-reviewed" "not-applicable" "verified" "low" "保留/按优先级整改" "章节级教学有效性、工具选型、实跑证据和剩余整改顺序已复核"
    } elseif ($relative -like "*\07_教材章节质量契约.md") {
        Set-Classification $row "content-reviewed" "not-applicable" "verified" "low" "保留/逐步结构化" "目标、练习、来源、代码角色和门禁分级工作契约"
    } elseif ($relative -like "*\08_自学教材规范符合性与首批改造报告_2026-07-12.md") {
        Set-Classification $row "content-reviewed" "not-applicable" "verified" "low" "保留/按证据更新" "自学规范映射、首批改造证据、适用边界和后续优先级已复核"
    } elseif ($relative -like "*\09_权威技术学习文档格式对标与教材内容检查_2026-07-12.md") {
        Set-Classification $row "content-reviewed" "not-applicable" "verified" "low" "保留为历史报告" "2026-07-12 对 22 份教材、202 章的历史检查；现行 210 章证据见 2026-07-18 artifact"
    } elseif (
        $relative -like "10_学习模块\F02_*\F02_*_适配教材.md" -or
        $relative -like "10_学习模块\F03_*\F03_*_适配教材.md" -or
        $relative -like "10_学习模块\F05_*\F05_*_适配教材.md" -or
        $relative -like "10_学习模块\F06_*\F06_*_适配教材.md" -or
        $relative -like "10_学习模块\F08_*\F08_*_适配教材.md" -or
        $relative -like "10_学习模块\M04_*\M04_*_适配教材.md" -or
        $relative -like "10_学习模块\M06_*\M06_*_适配教材.md" -or
        $relative -like "10_学习模块\M08_*\M08_*_适配教材.md"
    ) {
        Set-Classification $row "draft" "not-applicable" "unverified" "medium" "保留/继续教程闭环" "Wave 0 事实、安全和跨章契约已修复，Wave 1 入口和章级类型已完成；worked example、章内来源或教程反馈仍未全部达到 content-reviewed" "" "补齐对应 instructional 章的示例、来源、反馈与清理后逐章评估 content-reviewed"
    } elseif ($relative -like "10_学习模块\M12_*\M12_*_适配教材.md") {
        Set-Classification $row "draft" "not-applicable" "unverified" "medium" "保留为 design-note/补激活证据" "稳定引用、检索前权限、claim-support、owner-scoped 幂等和设计边界已补；P03 金融 task 仍未注册" "" "具备授权语料、已注册任务和端到端结果后再增加 instructional/workbook 内容"
    } elseif (
        $relative -like "10_学习模块\F00_金融市场与资产基础\F00_*_适配教材.md" -or
        $relative -like "10_学习模块\F01_概率统计与数学基础\F01_*_适配教材.md" -or
        $relative -like "10_学习模块\F03_投资组合与风险管理\F03_*_适配教材.md" -or
        $relative -like "10_学习模块\M03_RAG工程\M03_*_适配教材.md" -or
        $relative -like "10_学习模块\M09_Kubernetes与云原生\M09_*_适配教材.md"
    ) {
        Set-Classification $row "draft" "not-applicable" "unverified" "medium" "保留/继续教程闭环" "首批教学闭环和局部可执行证据已复核，入口与章级类型已完成；章内来源和首次教学证据仍不均匀" "" "按 instructional 章补 worked example、来源、反馈和章末衔接后评估 content-reviewed"
    } elseif (
        ($relative -like "10_学习模块\*\*_适配教材.md" -or
         $relative -like "10_学习模块\*\*_章节教材.md") -and
        $relative -notlike "*\99_归档\*"
    ) {
        Set-Classification $row "draft" "not-applicable" "unverified" "medium" "保留/按 09 报告修订" "210 章已人工归类，其中 166 章为 instructional，且 22 份入口齐全；对应 instructional 文档闭环尚未全部达到 content-reviewed" "" "完成 09 报告 Wave 2-3 项并通过人工语义复核"
    } elseif ($relative -like "10_学习模块\M05_任务队列与调度\教材章节\*") {
        Set-Classification $row "draft" "not-applicable" "unverified" "medium" "保留/继续答案隔离" "M05 无损拆分章节；结构和代码块已验证，完整答案与固定结果仍需逐章隔离"
    } elseif ($relative -like "10_学习模块\M05_任务队列与调度\M05_参考答案与结果索引.md") {
        Set-Classification $row "content-reviewed" "not-applicable" "verified" "low" "保留" "只提供完成后 reference 导航，不复制答案"
    } elseif ($relative -like "40_实验练习\E05_调度实验\E05-05*" -or $relative -like "40_实验练习\E05_调度实验\E05-06*") {
        Set-Classification $row "content-reviewed" "runnable-task" "unverified" "medium" "保留/学习者复现" "新增独立学习者任务，提供接口、不变量和验收，不提供完整答案" "M05 对应章节" "学习者保存代码、原始 artifact、复现命令和证据表"
    } elseif ($relative -like "40_实验练习\E00_工具链基础实验\os_network_reference\*") {
        Set-Classification $row "content-reviewed" "executable" "verified" "medium" "保留" "进程元数据、超时回收、信号清理、权限恢复和请求路径故障分类 reference，共 11 项测试通过"
    } elseif ($relative -like "40_实验练习\E01_Python基础练习\concurrency_reference\*") {
        Set-Classification $row "content-reviewed" "executable" "verified" "medium" "保留" "线程池、进程池、asyncio 和取消清理 reference，共 6 项测试通过"
    } elseif (
        $relative -like "40_实验练习\E00_工具链基础实验\*.md" -or
        $relative -like "40_实验练习\E01_Python基础练习\*.md" -or
        $relative -like "40_实验练习\E04_Agent实验\*.md"
    ) {
        $implementation = if ($relative -like "*_索引.md") { "partial" } else { "runnable-task" }
        Set-Classification $row "draft" $implementation "unverified" "medium" "保留/学习者复现" "当前学习入口或实验题面已存在；reference 与学习者运行证据分离，尚未完成学习者验证"
    } elseif ($relative -like "00_路线总控\审计与整改\*") {
        Set-Classification $row "draft" "not-applicable" "unverified" "medium" "人工复核" "整改控制文件已纳入覆盖清单，但未由路径规则授予内容成熟度或低风险结论"
    } elseif ($relative -like "40_实验练习\E02_后端API实验\e02_service\*") {
        Set-Classification $row "content-reviewed" "executable" "verified" "medium" "保留" "FastAPI 生命周期、跨租户隔离、幂等并发契约和自包含 OpenAPI schema reference，共 29 项测试通过"
    } elseif ($relative -like "40_实验练习\E03_RAG实验\e03_rag_reference\*") {
        Set-Classification $row "content-reviewed" "executable" "verified" "medium" "保留" "固定 corpus/黄金集、三路检索、权限前置过滤、多格式解析质量、并发 retention/cache lineage 删除和离线 generation 输出评估闭环，共 154 项测试通过"
    } elseif ($relative -like "40_实验练习\E04_Agent实验\e04_runtime_reference\*") {
        Set-Classification $row "content-reviewed" "executable" "verified" "medium" "保留" "确定性 Agent runtime、授权审批、fencing、versioned reducer/checkpoint、异常时序、跨租户隔离和审计，共 86 项测试通过"
    } elseif ($relative -like "40_实验练习\E06_数据库异步任务实验\e06_sqlite_reference\*") {
        Set-Classification $row "content-reviewed" "executable" "verified" "medium" "保留" "E06 42 项测试覆盖 owner/ACL schema v2、FastAPI、SQLite outbox/worker fencing 和安全 cache-aside；真实 Redis 与跨进程协调仍属边界"
    } elseif ($relative -like "40_实验练习\GF10_*\finance_reference\*") {
        Set-Classification $row "content-reviewed" "executable" "verified" "medium" "保留" "金融 P0 参考实现，9 个测试通过"
    } elseif ($relative -like "40_实验练习\E09_K8s实验\kind_reference\*") {
        Set-Classification $row "content-reviewed" "executable" "verified" "medium" "保留/学习者复现" "kind 多服务、权限/重启路径和手工 1/2/4 worker 功能性 reference 已验证；无 HPA 或生产化结论"
    } elseif ($relative -like "40_实验练习\E10_推理服务实验\e10_inference_reference\*") {
        Set-Classification $row "content-reviewed" "executable" "verified" "medium" "保留" "确定性推理 workload 和指标参考实现，7 个测试通过"
    } elseif ($relative -like "50_项目产出\P03_AI_Workload_Platform\p03_service\*") {
        Set-Classification $row "content-reviewed" "executable" "verified" "medium" "保留" "P03 v0.3.1：27 项测试、RAG 安全边界、Redis Streams、固定时间表 sender、五服务故障闭环和 1/2/4 worker × 3 随机化本机 reference 已验证"
    } elseif ($relative -like "50_项目产出\P01_Mini_Scheduler\mini_scheduler\*") {
        $implementation = if ($file.Extension -eq ".md") { "not-applicable" } else { "executable" }
        Set-Classification $row "content-reviewed" $implementation "verified" "medium" "保留" "P01 参考实现 28 个测试通过；教学与 RQ01 E2 pilot artifacts 已刷新"
    } elseif ($relative -like "50_项目产出\P01_Mini_Scheduler\*") {
        Set-Classification $row "content-reviewed" "partial" "verified" "medium" "保留/继续学习者复现" "P01 reference 与 30-seed E2 pilot 已验证；学习者复现和真实服务场景仍未完成"
    } elseif ($relative -like "40_实验练习\E09_K8s实验\E09-01*") {
        Set-Classification $row "content-reviewed" "executable" "verified" "medium" "保留/学习者复现" "kind v0.32.0 集群创建、节点检查和清理已通过" "kind_reference" "学习者独立创建、检查并清理 kind 集群"
    } elseif ($relative -like "40_实验练习\E09_K8s实验\E09-02*") {
        Set-Classification $row "content-reviewed" "executable" "verified" "medium" "保留/学习者复现" "五服务 Deployment/Service、probe、非 root、权限路径和 API rollout 持久性已在 kind 验证" "E09-01" "学习者完成 rollout、权限、重启持久性和清理"
    } elseif ($relative -like "40_实验练习\E09_K8s实验\E09-03*") {
        Set-Classification $row "content-reviewed" "executable" "verified" "medium" "保留/继续实验" "kind 手工 1/2/4 replicas 功能对照已验证；单次时延不作性能结论" "E09-02" "学习者复现，再补重复实验或 HPA/KEDA"
    } elseif ($relative -like "40_实验练习\E09_K8s实验\E09-04*") {
        Set-Classification $row "content-reviewed" "not-applicable" "unverified" "medium" "保留为概念实验" "只做 Kueue/admission/scheduler 边界映射"
    } elseif ($relative -like "40_实验练习\E09_K8s实验\*") {
        Set-Classification $row "content-reviewed" "partial" "verified" "medium" "保留/继续实现" "E09-01/02/03 已有 kind 功能性 reference；E09-04、自动扩缩容和生产化未实现"
    } elseif ($relative -like "40_实验练习\E10_推理服务实验\E10-01*" -or $relative -like "40_实验练习\E10_推理服务实验\E10-02*") {
        Set-Classification $row "content-reviewed" "executable" "verified" "medium" "保留" "确定性模拟实验已通过 7 个测试"
    } elseif ($relative -like "40_实验练习\E10_推理服务实验\E10-03*") {
        Set-Classification $row "content-reviewed" "absent" "unverified" "high" "保留/环境阻塞" "vLLM 需独立 Linux/WSL、驱动、模型和显存前提" "Linux/WSL + GPU" "真实 streaming 请求和指标记录完整"
    } elseif ($relative -like "40_实验练习\E10_推理服务实验\*") {
        Set-Classification $row "content-reviewed" "partial" "verified" "medium" "保留" "模拟实验 verified，真实 vLLM blocked"
    } elseif ($relative -like "40_实验练习\E07_Docker实验\E07-01*") {
        Set-Classification $row "content-reviewed" "executable" "verified" "medium" "保留" "P03 单 API 容器已通过健康检查和 HTTP 闭环"
    } elseif ($relative -like "40_实验练习\E07_Docker实验\E07-02*" -or $relative -like "40_实验练习\E07_Docker实验\E07-03*") {
        Set-Classification $row "content-reviewed" "executable" "verified" "medium" "保留" "PostgreSQL/Redis/outbox dispatcher/独立 worker 与故障恢复已验证"
    } elseif ($relative -like "40_实验练习\E07_Docker实验\*") {
        Set-Classification $row "content-reviewed" "executable" "verified" "medium" "保留" "E07-01 至 E07-03 reference 均已验证"
    } elseif ($relative -like "40_实验练习\E08_监控压测实验\E08-01*" -or $relative -like "40_实验练习\E08_监控压测实验\E08-02*") {
        Set-Classification $row "content-reviewed" "executable" "verified" "medium" "保留/继续正式实验" "Locust、task 分位数、队列/资源时序和三次随机化本机 reference 已验证；学习者长时实验未完成"
    } elseif ($relative -like "40_实验练习\E08_监控压测实验\E08-03*") {
        Set-Classification $row "content-reviewed" "executable" "verified" "medium" "保留/继续正式实验" "1/2/4 worker × 3 随机化本机对照、队列/资源时序和 95% t 区间已验证"
    } elseif ($relative -like "40_实验练习\E08_监控压测实验\*") {
        Set-Classification $row "content-reviewed" "executable" "verified" "medium" "保留/继续正式实验" "E08-01/02/03 均有三次随机化本机 reference；长时、真实 workload 和学习者复现未完成"
    } elseif ($relative -like "60_科研训练\研究项目\RQ01_*\artifacts\rq01_e2_pilot_20260711\*") {
        Set-Classification $row "content-reviewed" "not-applicable" "verified" "medium" "保留/继续实验" "30-seed E2 合成 pilot、原始 workload/task、paired bootstrap 和 SHA-256 已验证；不是场景结论"
    } elseif ($relative -like "60_科研训练\研究项目\RQ01_*\*") {
        Set-Classification $row "content-reviewed" "partial" "verified" "medium" "保留/继续实现" "E2 synthetic pilot 已完成；Pareto/burst、P03 replay 和场景 trace 未完成" "P03 fixed-arrival replay" "扩展条件并完成服务回放"
    } elseif ($relative -like "40_实验练习\E02_后端API实验\*") {
        Set-Classification $row "content-reviewed" "executable" "verified" "medium" "保留" "文档已对齐单一 FastAPI 项目"
    } elseif ($relative -like "40_实验练习\E03_RAG实验\*") {
        Set-Classification $row "content-reviewed" "partial" "verified" "medium" "保留" "检索、权限、多格式 ingestion、lineage 删除与 simulated generation evaluator 已验证；真实模型 generation 和生产解析隔离仍为 partial"
    } elseif ($relative -like "40_实验练习\E06_数据库异步任务实验\*") {
        Set-Classification $row "content-reviewed" "partial" "verified" "medium" "保留" "SQLite 语义闭环与 P03 PostgreSQL/Redis 多服务 reference 均已验证"
    } elseif ($relative -like "40_实验练习\GF00_*\GF02-01*" -or
              $relative -like "40_实验练习\GF10_*\GF05-01*" -or
              $relative -like "40_实验练习\GF10_*\GF05-02*" -or
              $relative -like "40_实验练习\GF10_*\GF07-01*" -or
              $relative -like "40_实验练习\GF10_*\GF08-01*") {
        Set-Classification $row "content-reviewed" "partial" "verified" "medium" "保留" "金融 P0 错误已修并有参考测试"
    } elseif ($relative -like "50_项目产出\P03_AI_Workload_Platform\*") {
        Set-Classification $row "draft" "partial" "verified" "medium" "小修/继续实现" "v0.3.1 内存、多服务、权限前置过滤 RAG retrieval、短时负载和 kind 功能性 reference 已验证；generation/Agent/K8s 生产化仍 planned"
    }

    $row
}

$rows |
    Sort-Object file |
    Export-Csv -LiteralPath $matrixPath -NoTypeInformation -Encoding utf8

Write-Output "matrix_rows=$($rows.Count)"
