param(
    [string]$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..\..")),
    [string]$ReportPath = ""
)

$ErrorActionPreference = "Stop"
$utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8
$root = (Resolve-Path $RepositoryRoot).Path
$auditRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$dateStamp = Get-Date -Format "yyyy-MM-dd"
$report = if ($ReportPath) {
    Join-Path $root $ReportPath
} else {
    Join-Path $auditRoot "artifacts\content_quality_audit_$dateStamp\mermaid_validation.json"
}
$renderRoot = Join-Path $root ".tools\content-quality\mermaid-render\11.16.0"
$npx = (Get-Command npx.cmd).Source
New-Item -ItemType Directory -Force -Path $renderRoot | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path $report -Parent) | Out-Null

function Get-RepositoryRelativePath {
    param([Parameter(Mandatory = $true)][string]$Path)

    return $Path.Substring($root.Length).TrimStart("\").Replace("\", "/")
}

Push-Location $root
try {
    $files = @(
        Get-ChildItem -LiteralPath $root -Recurse -File -Filter "*.md" |
            Where-Object {
                $_.FullName -notmatch "[\\/](?:\.tools|\.venv|node_modules)(?:[\\/]|$)" -and
                [IO.File]::ReadAllText($_.FullName).Contains('```mermaid')
            } |
            ForEach-Object { $_.FullName }
    )
    if ($files.Count -eq 0) {
        throw "no Mermaid documents found"
    }

    $rows = @()
    $index = 0
    $ErrorActionPreference = "Continue"
    foreach ($file in $files) {
        $index += 1
        $output = Join-Path $renderRoot ("document-{0:D2}.md" -f $index)
        $stdout = Join-Path $renderRoot ("document-{0:D2}.stdout.log" -f $index)
        $stderr = Join-Path $renderRoot ("document-{0:D2}.stderr.log" -f $index)
        & $npx --yes "@mermaid-js/mermaid-cli@11.16.0" `
            -i $file -o $output 1> $stdout 2> $stderr
        $renderExit = $LASTEXITCODE
        foreach ($log in @($stdout, $stderr)) {
            if (Test-Path -LiteralPath $log) {
                $content = [IO.File]::ReadAllText($log)
                [IO.File]::WriteAllText($log, $content, $utf8)
            }
        }
        $rows += [ordered]@{
            file = Get-RepositoryRelativePath -Path $file
            exit_code = $renderExit
            rendered_markdown = Get-RepositoryRelativePath -Path $output
            stdout = Get-RepositoryRelativePath -Path $stdout
            stderr = Get-RepositoryRelativePath -Path $stderr
        }
    }
    $ErrorActionPreference = "Stop"

    $result = [ordered]@{
        tool = "@mermaid-js/mermaid-cli"
        version = "11.16.0"
        document_count = $rows.Count
        failed_document_count = @($rows | Where-Object { $_.exit_code -ne 0 }).Count
        documents = $rows
    }
    $result | ConvertTo-Json -Depth 5 | Out-File -LiteralPath $report -Encoding utf8
    Write-Output "mermaid_report=$report"
    Write-Output "documents=$($result.document_count) failures=$($result.failed_document_count)"
    if ($result.failed_document_count -ne 0) {
        exit 1
    }
} finally {
    Pop-Location
}
