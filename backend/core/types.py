from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class HighItem(BaseModel):
    """蓝海列表单行数据结构，字段参考 mengla-type.md / 前端 BlueSea 表格使用字段。"""

    catNameCn: Optional[str] = None
    catName: Optional[str] = None
    catTag: Optional[int] = None

    catId1: Optional[str] = None
    catId2: Optional[str] = None
    catId3: Optional[str] = None

    skuNum: Optional[int] = None
    saleSkuNum: Optional[int] = None
    saleRatio: Optional[float] = None

    monthSales: Optional[float] = None
    monthSalesRating: Optional[float] = None
    monthSalesDynamics: Optional[float] = None

    monthGmv: Optional[float] = None
    monthGmvRmb: Optional[float] = None
    monthGmvRating: Optional[float] = None
    monthGmvDynamics: Optional[float] = None

    brand: Optional[str] = None
    brandGmv: Optional[float] = None
    brandGmvRmb: Optional[float] = None
    brandGmvRating: Optional[float] = None

    topGmv: Optional[float] = None
    topGmvRating: Optional[float] = None
    topAvgPrice: Optional[float] = None
    topAvgPriceRmb: Optional[float] = None


class IndustryRangeBucket(BaseModel):
    """行业区间分布中的单个区间桶。"""

    id: Optional[str] = None
    title: Optional[str] = None

    itemCount: Optional[int] = None
    sales: Optional[float] = None
    gmv: Optional[float] = None

    itemCountRate: Optional[float] = None
    salesRate: Optional[float] = None
    gmvRate: Optional[float] = None


class IndustryBrandRateItem(BaseModel):
    """行业子类目占比条目。"""

    catId: Optional[str] = None
    catName: Optional[str] = None
    catNameCn: Optional[str] = None

    brandGmv: Optional[float] = None
    brandGmvRate: Optional[float] = None

    brandItemCount: Optional[int] = None
    brandItemCountRate: Optional[float] = None

    brandSales: Optional[float] = None
    brandSalesRate: Optional[float] = None

    typeId: Optional[str] = None


class IndustryViewPayload(BaseModel):
    """行业区间视图完整 payload 结构。"""

    industrySalesRangeDtoList: List[IndustryRangeBucket] = []
    industryGmvRangeDtoList: List[IndustryRangeBucket] = []
    industryPriceRangeDtoList: List[IndustryRangeBucket] = []
    industryBrandRateDtoList: List[IndustryBrandRateItem] = []


class IndustryTrendPoint(BaseModel):
    """行业趋势单个时间点数据。"""

    timest: Optional[str] = None

    salesSkuCount: Optional[int] = None
    salesSkuRatio: Optional[float] = None

    monthSales: Optional[float] = None
    monthSalesRatio: Optional[float] = None

    monthGmv: Optional[float] = None
    monthGmvRatio: Optional[float] = None

    currentDayPrice: Optional[float] = None


class HighResponse(BaseModel):
    """蓝海接口在 Mongo/Redis 中存储的统一结构。"""

    list: List[HighItem] = []


class IndustryViewResponse(BaseModel):
    """行业视图接口统一结构。"""

    industryViewV2List: IndustryViewPayload


class IndustryTrendResponse(BaseModel):
    """行业趋势接口统一结构。"""

    industryTrendRange: List[IndustryTrendPoint]

