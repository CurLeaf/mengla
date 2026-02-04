# 清理旧版数据脚本
# 
# 使用方法：
#   .\cleanup_legacy.ps1           # 预览模式
#   .\cleanup_legacy.ps1 -Confirm  # 执行删除
#   .\cleanup_legacy.ps1 -Confirm -Redis  # 同时清理 Redis

param(
    [switch]$Confirm,
    [switch]$Redis
)

Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host "  MengLa 旧数据清理工具" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

$args = @()

if ($Confirm) {
    Write-Host "[!] 即将执行删除操作" -ForegroundColor Yellow
    $args += "--confirm"
} else {
    Write-Host "[预览模式] 不会实际删除数据" -ForegroundColor Green
    $args += "--dry-run"
}

if ($Redis) {
    Write-Host "[+] 将同时清理 Redis 缓存" -ForegroundColor Yellow
    $args += "--redis"
}

Write-Host ""

# 执行 Python 脚本
python -m backend.tools.cleanup_legacy @args
