# 方案 A Monorepo 迁移脚本
# 用法：在仓库根目录执行 .\scripts\migrate-monorepo.ps1
# 职责：创建根目录 pnpm-workspace.yaml、package.json，执行 pnpm install，删除 frontend/pnpm-lock.yaml

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot

# 1. 写入 pnpm-workspace.yaml
$WorkspaceYaml = @"
packages:
  - "frontend"
"@
$WorkspacePath = Join-Path $RepoRoot "pnpm-workspace.yaml"
try {
    Set-Content -Path $WorkspacePath -Value $WorkspaceYaml -Encoding UTF8
    Write-Host "[OK] 已写入 $WorkspacePath"
} catch {
    Write-Error "写入 pnpm-workspace.yaml 失败: $_"
    exit 1
}

# 2. 写入根 package.json
$PackageJson = @"
{
  "name": "mengla-data-collect",
  "private": true,
  "scripts": {
    "dev": "pnpm --filter industry-monitor-frontend dev",
    "build": "pnpm --filter industry-monitor-frontend build",
    "preview": "pnpm --filter industry-monitor-frontend preview"
  },
  "devDependencies": {
    "typescript": "~5.6.3"
  }
}
"@
$PackagePath = Join-Path $RepoRoot "package.json"
try {
    Set-Content -Path $PackagePath -Value $PackageJson.TrimEnd() -Encoding UTF8
    Write-Host "[OK] 已写入 $PackagePath"
} catch {
    Write-Error "写入 package.json 失败: $_"
    exit 1
}

# 3. 在根目录执行 pnpm install
Push-Location $RepoRoot
try {
    & pnpm install
    if ($LASTEXITCODE -ne 0) {
        Write-Error "pnpm install 失败 (exit code $LASTEXITCODE)"
        exit 1
    }
    Write-Host "[OK] pnpm install 完成"
} finally {
    Pop-Location
}

# 4. 删除 frontend/pnpm-lock.yaml（若存在）
$FrontendLock = Join-Path (Join-Path $RepoRoot "frontend") "pnpm-lock.yaml"
if (Test-Path $FrontendLock) {
    Remove-Item $FrontendLock -Force
    Write-Host "[OK] 已删除 frontend/pnpm-lock.yaml"
} else {
    Write-Host "[--] frontend/pnpm-lock.yaml 不存在，跳过"
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Plan A migration done." -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Run from repo root: pnpm dev, pnpm build, pnpm preview"
Write-Host ""
