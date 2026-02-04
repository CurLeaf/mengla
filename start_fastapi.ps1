# PowerShell 脚本：启动 FastAPI 服务
# 用法：.\start_fastapi.ps1

Write-Host "================================" -ForegroundColor Cyan
Write-Host "启动 FastAPI 服务" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "监听端口: 8000" -ForegroundColor Gray
Write-Host "Webhook 端点: /api/webhook/mengla-notify" -ForegroundColor Gray
Write-Host ""
Write-Host "按 Ctrl+C 停止服务" -ForegroundColor Yellow
Write-Host "================================" -ForegroundColor Cyan
Write-Host ""

# 启动 FastAPI
uvicorn backend.main:app --reload --port 8000
