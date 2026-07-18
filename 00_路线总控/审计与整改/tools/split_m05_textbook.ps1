param(
    [string]$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\.."))
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path $RepositoryRoot).Path
$moduleRoot = Join-Path $root "10_学习模块\M05_任务队列与调度"
$source = Join-Path $moduleRoot "M05_任务队列与调度_章节教材.md"
$chapterRoot = Join-Path $moduleRoot "教材章节"
$artifactRoot = Join-Path $root "00_路线总控\审计与整改\artifacts\m05_split_2026-07-11"
$utf8 = New-Object System.Text.UTF8Encoding($false)

$text = [IO.File]::ReadAllText($source, $utf8)
$newline = if ($text.Contains("`r`n")) { "`r`n" } else { "`n" }
$lines = [regex]::Split($text.TrimEnd("`r", "`n"), "\r?\n")

$chapters = @(
    [ordered]@{ number = 0; start = 119; end = 303; file = "00_这门小教材怎么学.md" },
    [ordered]@{ number = 1; start = 304; end = 652; file = "01_为什么调度不是简单排序.md" },
    [ordered]@{ number = 2; start = 653; end = 1381; file = "02_Task_Worker_Queue_最小模型.md" },
    [ordered]@{ number = 3; start = 1382; end = 2002; file = "03_FIFO_baseline.md" },
    [ordered]@{ number = 4; start = 2003; end = 2576; file = "04_Priority_和业务优先级.md" },
    [ordered]@{ number = 5; start = 2577; end = 3153; file = "05_SJF_和平均等待时间.md" },
    [ordered]@{ number = 6; start = 3154; end = 3775; file = "06_指标_average_P95_P99_utilization.md" },
    [ordered]@{ number = 7; start = 3776; end = 4621; file = "07_高峰负载实验.md" },
    [ordered]@{ number = 8; start = 4622; end = 5366; file = "08_Cost-aware_调度.md" },
    [ordered]@{ number = 9; start = 5367; end = 5979; file = "09_分组分析_谁被牺牲了.md" },
    [ordered]@{ number = 10; start = 5980; end = 6690; file = "10_Aging_最大等待保护.md" },
    [ordered]@{ number = 11; start = 6691; end = 7338; file = "11_多_worker_与资源利用率.md" },
    [ordered]@{ number = 12; start = 7339; end = 7817; file = "12_项目总结与复盘.md" }
)

[IO.Directory]::CreateDirectory($chapterRoot) | Out-Null
[IO.Directory]::CreateDirectory($artifactRoot) | Out-Null
$manifestPath = Join-Path $artifactRoot "manifest.json"

if ($lines.Count -ne 7826 -and (Test-Path -LiteralPath $manifestPath)) {
    Write-Output "m05_split=already_completed"
    Write-Output "manifest=$manifestPath"
    exit 0
}

$isFreshSource = $lines.Count -eq 7826
$originalSha = $null

if ($isFreshSource) {
    $originalSha = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()

    foreach ($chapter in $chapters) {
        $target = Join-Path $chapterRoot $chapter.file
        if (Test-Path -LiteralPath $target) {
            throw "Refusing to overwrite existing chapter: $target"
        }

        $chapterText = ($lines[($chapter.start - 1)..($chapter.end - 1)] -join $newline) + $newline
        [IO.File]::WriteAllText($target, $chapterText, $utf8)
        $chapter["line_count"] = $chapter.end - $chapter.start + 1
        $chapter["sha256"] = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant()
    }

    $indexLines = New-Object System.Collections.Generic.List[string]
    foreach ($line in $lines[0..117]) {
        $indexLines.Add($line)
    }

    $indexLines.Add("## 拆分后的章节入口")
    $indexLines.Add("")
    $indexLines.Add("正文已经按章拆分。下面保留原章节标题作为旧链接兼容锚点；新学习记录应直接链接到独立章节文件。")
    $indexLines.Add("")

    foreach ($chapter in $chapters) {
        $title = $lines[$chapter.start - 1].Substring(2)
        $stem = [IO.Path]::GetFileNameWithoutExtension($chapter.file)
        $indexLines.Add("## $title")
        $indexLines.Add("")
        $indexLines.Add("- [[$("10_学习模块/M05_任务队列与调度/教材章节/$stem")|打开本章正文]]")
        $indexLines.Add("")
    }

    $indexLines.Add("## M05 全书完成说明")
    foreach ($line in $lines[7818..7825]) {
        $indexLines.Add($line)
    }

    $indexText = ($indexLines -join $newline) + $newline
    [IO.File]::WriteAllText($source, $indexText, $utf8)
} else {
    if (-not $text.Contains("## 拆分后的章节入口")) {
        throw "M05 is neither the expected 7826-line source nor a recognized split index."
    }

    $chapterText = New-Object System.Text.StringBuilder
    foreach ($chapter in $chapters) {
        $target = Join-Path $chapterRoot $chapter.file
        if (-not (Test-Path -LiteralPath $target)) {
            throw "Split recovery is missing chapter: $target"
        }

        $targetLines = Get-Content -LiteralPath $target -Encoding UTF8
        $expectedLines = $chapter.end - $chapter.start + 1
        if ($targetLines.Count -ne $expectedLines) {
            throw "Chapter $($chapter.file) has $($targetLines.Count) lines; expected $expectedLines."
        }

        $chapter["line_count"] = $expectedLines
        $chapter["sha256"] = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant()
        [void]$chapterText.Append([IO.File]::ReadAllText($target, $utf8))
    }

    $completionIndex = [Array]::IndexOf([string[]]$lines, "## M05 全书完成说明")
    if ($completionIndex -lt 0) {
        throw "Split index is missing the completion heading."
    }

    $introText = ($lines[0..117] -join $newline) + $newline
    $completionText = "# M05 全书完成说明$newline" + `
        ($lines[($completionIndex + 1)..($lines.Count - 1)] -join $newline) + $newline
    $reconstructed = $introText + $chapterText.ToString() + $completionText
    $reconstructedLines = [regex]::Split($reconstructed.TrimEnd("`r", "`n"), "\r?\n")
    if ($reconstructedLines.Count -ne 7826) {
        throw "Reconstructed source has $($reconstructedLines.Count) lines; expected 7826."
    }

    $sha256 = [Security.Cryptography.SHA256]::Create()
    try {
        $hashBytes = $sha256.ComputeHash($utf8.GetBytes($reconstructed))
    } finally {
        $sha256.Dispose()
    }
    $originalSha = ([BitConverter]::ToString($hashBytes)).Replace("-", "").ToLowerInvariant()
}

$manifest = [ordered]@{
    schema_version = "1.0"
    source = "10_学习模块/M05_任务队列与调度/M05_任务队列与调度_章节教材.md"
    original_line_count = 7826
    original_sha256 = $originalSha
    preserved_intro_range = "1-118"
    preserved_completion_range = "7818-7826"
    chapter_line_count = ($chapters | ForEach-Object { [int]$_["line_count"] } | Measure-Object -Sum).Sum
    chapters = $chapters
}

$manifestJson = $manifest | ConvertTo-Json -Depth 6
[IO.File]::WriteAllText($manifestPath, $manifestJson + $newline, $utf8)

Write-Output "m05_split=completed"
Write-Output "chapter_count=$($chapters.Count)"
Write-Output "chapter_lines=$($manifest.chapter_line_count)"
Write-Output "manifest=$manifestPath"
