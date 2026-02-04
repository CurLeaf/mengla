@echo off
REM 批处理脚本：运行测试采集脚本
REM 用法：双击运行或在 CMD 中运行 run_test.bat
REM 前提：FastAPI 服务必须运行（使用 start_fastapi.bat）

echo ================================
echo 运行测试采集脚本
echo ================================
echo.
echo 采集范围: 近一个月
echo 颗粒度: 月、季、年
echo 接口: high, hot, chance, industryViewV2, industryTrendRange
echo.
echo 按 Ctrl+C 中断采集
echo ================================
echo.

python -m backend.test_one_month
