@echo off
chcp 65001 >nul
echo 正在启动模拟数据源服务...
echo 服务地址: http://localhost:3001
echo.

cd /d %~dp0

rem 激活虚拟环境（如果存在）
if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
)

python -m uvicorn backend.mock_data_source:app --host 0.0.0.0 --port 3001 --reload
