@echo off
echo ========================================
echo 采集所有一级类目的近一年数据
echo ========================================
echo.
echo 此脚本将为 category.json 中的所有一级类目采集数据
echo 包括：住宅和花园、服装、美容和卫生等
echo 时间范围：近一年（日、月、季、年粒度）
echo.
python backend\collect_all_categories_one_year.py
pause
