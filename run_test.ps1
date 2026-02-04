# PowerShell 脚本：运行测试采集脚本
# 用法：.\run_test.ps1
# 前提：FastAPI 服务必须运行（使用 start_fastapi.ps1）

Write-Host "================================" -ForegroundColor Cyan
Write-Host "运行测试采集脚本" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan
Write-Host ""

# 检查 FastAPI 是否运行
Write-Host "检查 FastAPI 服务..." -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8000/health" -TimeoutSec 2 -UseBasicParsing 2>$null
    if ($response.StatusCode -eq 200) {
        Write-Host "✓ FastAPI 服务正在运行" -ForegroundColor Green
    } else {
        Write-Host "✗ FastAPI 服务响应异常" -ForegroundColor Red
        Write-Host "  请先启动 FastAPI: .\start_fastapi.ps1" -ForegroundColor Yellow
        exit 1
    }
} catch {
    Write-Host "✗ FastAPI 服务未运行" -ForegroundColor Red
    Write-Host "  请先在另一个终端运行: .\start_fastapi.ps1" -ForegroundColor Yellow
    Write-Host "  或手动运行: uvicorn backend.main:app --reload --port 8000" -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "采集范围: 近一个月" -ForegroundColor Gray
Write-Host "颗粒度: 月、季、年" -ForegroundColor Gray
Write-Host "接口: high, hot, chance, industryViewV2, industryTrendRange" -ForegroundColor Gray
Write-Host ""
Write-Host "按 Ctrl+C 中断采集" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan
Write-Host ""

# 运行测试脚本
python -m backend.test_one_month
