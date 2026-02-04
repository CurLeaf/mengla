Write-Host "========================================"
Write-Host "采集所有一级类目的近一年数据"
Write-Host "========================================"
Write-Host ""
Write-Host "此脚本将为 category.json 中的所有一级类目采集数据"
Write-Host "包括：住宅和花园、服装、美容和卫生等"
Write-Host "时间范围：近一年（日、月、季、年粒度）"
Write-Host ""

python backend\collect_all_categories_one_year.py

Write-Host ""
Write-Host "按任意键退出..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
