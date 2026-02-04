# 启动模拟数据源服务
# Mock Data Source Server - 模拟外部采集服务

Write-Host "正在启动模拟数据源服务..." -ForegroundColor Cyan
Write-Host "服务地址: http://localhost:3001" -ForegroundColor Yellow
Write-Host ""
Write-Host "API 端点:" -ForegroundColor Green
Write-Host "  GET  /api/status/processing  - 获取当前处理状态"
Write-Host "  GET  /api/status/queue       - 获取队列状态"
Write-Host "  GET  /health                 - 健康检查"
Write-Host ""

Set-Location $PSScriptRoot

# 激活虚拟环境（如果存在）
if (Test-Path "venv\Scripts\Activate.ps1") {
    . .\venv\Scripts\Activate.ps1
}

# 启动服务
python -m uvicorn backend.mock_data_source:app --host 0.0.0.0 --port 3001 --reload
