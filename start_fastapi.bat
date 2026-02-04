@echo off
REM 批处理脚本：启动 FastAPI 服务
REM 用法：双击运行或在 CMD 中运行 start_fastapi.bat

echo ================================
echo 启动 FastAPI 服务
echo ================================
echo.
echo 监听端口: 8000
echo Webhook 端点: /api/webhook/mengla-notify
echo.
echo 按 Ctrl+C 停止服务
echo ================================
echo.

uvicorn backend.main:app --reload --port 8000
