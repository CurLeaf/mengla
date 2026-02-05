import { useEffect, useMemo, useState, type ChangeEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { HotIndustryTable } from "./components/HotIndustryTable";
import { DistributionSection } from "./components/DistributionCards";
import { TrendChart } from "./components/TrendChart";
import { AdminCenterPage } from "./components/AdminCenter/AdminCenterPage";
import {
  getDefaultTimestForPeriod,
  periodToDateType,
  RankPeriodSelector,
  type PeriodType,
} from "./components/RankPeriodSelector";
import {
  getDefaultTrendRangeForPeriod,
  TrendPeriodRangeSelector,
} from "./components/TrendPeriodRangeSelector";
import { queryMengla } from "./services/mengla-api";
import { fetchCategories } from "./services/category-api";
import { fetchPanelConfig } from "./services/panel-config-api";
import type { Category, CategoryChild, CategoryList } from "./types/category";
import type {
  HighListRow,
  IndustryView,
  MenglaResponseData,
  TrendPoint,
} from "./types/mengla";

const MODES = [
  { key: "overview", name: "行业总览", badge: "OVERVIEW" },
  { key: "high", name: "蓝海Top行业", badge: "HIGH" },
  { key: "hot", name: "热销Top行业", badge: "HOT" },
  { key: "chance", name: "潜力Top行业", badge: "CHANCE" },
] as const;

type ModeKey = (typeof MODES)[number]["key"];
type AppView = ModeKey | "admin";

const VALID_PERIODS: PeriodType[] = ["update", "month", "quarter", "year"];

const SHOW_ADMIN_CENTER =
  import.meta.env.DEV || import.meta.env.VITE_ENABLE_ADMIN_CENTER === "true";

/** 季度 timest 规范为 yyyy-Qn（采集 API 要求） */
function normalizeQuarterTimest(timest: string): string {
  const s = (timest || "").trim();
  if (/^\d{4}-Q[1-4]$/i.test(s)) return s;
  const m = s.match(/^(\d{4})Q?([1-4])$/i);
  if (m) return `${m[1]}-Q${m[2]}`;
  return s;
}

/** 按当前选中的周期（更新日期/月榜/季榜/年榜）生成请求参数；industryViewV2 季榜用 QUARTERLY_FOR_YEAR + yyyy-Qn */
function buildQueryParams(
  action: string,
  primaryCatId: string,
  period: PeriodType,
  timest: string
) {
  const isViewV2Quarter =
    action === "industryViewV2" && period === "quarter";
  const dateType = isViewV2Quarter
    ? "QUARTERLY_FOR_YEAR"
    : periodToDateType(period);
  const normalizedTimest =
    isViewV2Quarter ? normalizeQuarterTimest(timest) : timest;
  return {
    action,
    product_id: "",
    catId: primaryCatId,
    dateType,
    timest: normalizedTimest,
    starRange: normalizedTimest,
    endRange: normalizedTimest,
  };
}

/** 行业趋势：dateType 由 trendPeriod 决定；starRange/endRange 按颗粒传——更新日期 yyyy-MM-dd，月榜 yyyy-MM，季榜 yyyy-Qn，年榜 yyyy */
function buildTrendQueryParams(
  action: string,
  primaryCatId: string,
  trendPeriod: PeriodType,
  starRange: string,
  endRange: string
) {
  return {
    action,
    product_id: "",
    catId: primaryCatId,
    dateType: periodToDateType(trendPeriod),
    timest: endRange,
    starRange,
    endRange,
  };
}

export default function App() {
  const [view, setView] = useState<AppView>("overview");
  const mode: ModeKey = view === "admin" ? "overview" : view;
  const [triggerLoading, setTriggerLoading] = useState(false);
  const [period, setPeriod] = useState<PeriodType>("month");
  const [timest, setTimest] = useState(() => getDefaultTimestForPeriod("month"));
  /** 行业总览趋势：四个 Tab（更新日期/月榜/季榜/年榜）+ 对应范围（日期/月/季/年） */
  const [trendPeriod, setTrendPeriod] = useState<PeriodType>("update");
  const [trendRangeStart, setTrendRangeStart] = useState(() =>
    getDefaultTrendRangeForPeriod("update").start
  );
  const [trendRangeEnd, setTrendRangeEnd] = useState(() =>
    getDefaultTrendRangeForPeriod("update").end
  );
  /** 行业区间分布：独立时间选择（不与行业趋势共用） */
  const [distributionPeriod, setDistributionPeriod] = useState<PeriodType>("update");
  const [distributionTimest, setDistributionTimest] = useState(() =>
    getDefaultTimestForPeriod("update")
  );

  const panelConfigQuery = useQuery({
    queryKey: ["panel-config"],
    queryFn: fetchPanelConfig,
    staleTime: 60 * 1000,
  });
  const panelConfig = panelConfigQuery.data;

  const effectiveModes = useMemo((): Array<{ key: ModeKey; name: string; badge: string }> => {
    const modules = panelConfig?.modules;
    if (!Array.isArray(modules) || modules.length === 0) {
      return [...MODES];
    }
    return modules
      .filter((m: { enabled?: boolean }) => m.enabled !== false)
      .sort((a: { order?: number }, b: { order?: number }) => (a.order ?? 0) - (b.order ?? 0))
      .map((m: { id: string; name: string }) => ({
        key: m.id as ModeKey,
        name: m.name,
        badge: m.id.toUpperCase(),
      }))
      .filter((m): m is { key: ModeKey; name: string; badge: string } =>
        MODES.some((def) => def.key === m.key)
      );
  }, [panelConfig?.modules]);

  const [defaultPeriodApplied, setDefaultPeriodApplied] = useState(false);
  useEffect(() => {
    if (defaultPeriodApplied || !panelConfig?.layout?.defaultPeriod) return;
    const defaultPeriod = panelConfig.layout.defaultPeriod as string;
    if (VALID_PERIODS.includes(defaultPeriod as PeriodType)) {
      setDefaultPeriodApplied(true);
      setPeriod(defaultPeriod as PeriodType);
      setTimest(getDefaultTimestForPeriod(defaultPeriod as PeriodType));
    }
  }, [panelConfig?.layout?.defaultPeriod, defaultPeriodApplied]);

  const showRankPeriodSelector = panelConfig?.layout?.showRankPeriodSelector !== false;

  useEffect(() => {
    // admin 是特殊视图，不需要检查 effectiveModes
    if (view === "admin") {
      if (!SHOW_ADMIN_CENTER) {
        setView(effectiveModes[0]?.key ?? "overview");
      }
      return;
    }
    const inList = effectiveModes.some((m) => m.key === view);
    if (!inList && effectiveModes.length > 0) {
      setView(effectiveModes[0].key);
    }
  }, [view, effectiveModes]);

  const [categories, setCategories] = useState<CategoryList>([]);
  const [selectedCatId1, setSelectedCatId1] = useState<string | null>(null);
  const [selectedCatId2, setSelectedCatId2] = useState<string | null>(null);

  const level2Options = useMemo(() => {
    if (!selectedCatId1 || !categories.length) return [];
    const first = categories.find(
      (c: Category) => String(c.catId) === selectedCatId1
    );
    return Array.isArray(first?.children) ? first!.children : [];
  }, [categories, selectedCatId1]);

  const primaryCatId = selectedCatId1 ?? "";

  const selectedCatLabel = useMemo(() => {
    if (!selectedCatId1 || !categories.length) return "全部类目";
    const first = categories.find(
      (c: Category) => String(c.catId) === selectedCatId1
    );
    const name1 = first ? first.catNameCn || first.catName || "" : "";
    if (!selectedCatId2) return name1 || "全部类目";
    const second = level2Options.find(
      (c: CategoryChild) => String(c.catId) === selectedCatId2
    );
    const name2 = second ? second.catNameCn || second.catName || "" : "";
    return name2 ? `${name1} > ${name2}` : name1;
  }, [categories, selectedCatId1, selectedCatId2, level2Options]);

  useEffect(() => {
    let cancelled = false;
    const loadCategories = async () => {
      try {
        const data = await fetchCategories();
        if (cancelled) return;
        setCategories(data || []);
        if (data?.length) {
          setSelectedCatId1((prev: string | null) =>
            prev === null ? String(data[0].catId) : prev
          );
        }
      } catch (e) {
        if (!cancelled) console.error("加载类目失败", e);
      }
    };
    loadCategories();
    return () => {
      cancelled = true;
    };
  }, []);

  const queryClient = useQueryClient();
  const dateType = periodToDateType(period);

  const overviewTrendQuery = useQuery({
    queryKey: [
      "mengla",
      "industryTrendRange",
      primaryCatId,
      trendPeriod,
      trendRangeStart,
      trendRangeEnd,
    ],
    queryFn: () => {
      const body = buildTrendQueryParams(
        "industryTrendRange",
        primaryCatId,
        trendPeriod,
        trendRangeStart,
        trendRangeEnd
      );
      return queryMengla(body);
    },
    enabled:
      !!primaryCatId && !!trendRangeStart && !!trendRangeEnd,
    staleTime: 5 * 60 * 1000,
    gcTime: 60 * 60 * 1000,
    networkMode: "always",
    retry: 2,
  });

  const overviewViewQuery = useQuery({
    queryKey: [
      "mengla",
      "industryViewV2",
      primaryCatId,
      distributionPeriod,
      distributionTimest,
    ],
    queryFn: () =>
      queryMengla(
        buildQueryParams(
          "industryViewV2",
          primaryCatId,
          distributionPeriod,
          distributionTimest
        )
      ),
    enabled: !!primaryCatId && !!distributionTimest,
    staleTime: 5 * 60 * 1000,
    gcTime: 60 * 60 * 1000,
    networkMode: "always",
    retry: 2,
  });

  const highQuery = useQuery({
    queryKey: ["mengla", "high", primaryCatId, dateType, timest],
    queryFn: () =>
      queryMengla(buildQueryParams("high", primaryCatId, period, timest)),
    enabled: !!primaryCatId && !!timest,
    staleTime: 5 * 60 * 1000,
    gcTime: 60 * 60 * 1000,
    networkMode: "always",
    retry: 2,
  });

  const hotQuery = useQuery({
    queryKey: ["mengla", "hot", primaryCatId, dateType, timest],
    queryFn: () =>
      queryMengla(buildQueryParams("hot", primaryCatId, period, timest)),
    enabled: !!primaryCatId && !!timest,
    staleTime: 5 * 60 * 1000,
    gcTime: 60 * 60 * 1000,
    networkMode: "always",
    retry: 2,
  });

  const chanceQuery = useQuery({
    queryKey: ["mengla", "chance", primaryCatId, dateType, timest],
    queryFn: () =>
      queryMengla(buildQueryParams("chance", primaryCatId, period, timest)),
    enabled: !!primaryCatId && !!timest,
    staleTime: 5 * 60 * 1000,
    gcTime: 60 * 60 * 1000,
    networkMode: "always",
    retry: 2,
  });

  const invalidateCurrent = () => {
    if (mode === "overview") {
      queryClient.invalidateQueries({
        queryKey: [
          "mengla",
          "industryTrendRange",
          primaryCatId,
          trendPeriod,
          trendRangeStart,
          trendRangeEnd,
        ],
      });
      queryClient.invalidateQueries({
        queryKey: [
          "mengla",
          "industryViewV2",
          primaryCatId,
          distributionPeriod,
          distributionTimest,
        ],
      });
    } else {
      queryClient.invalidateQueries({
        queryKey: ["mengla", mode, primaryCatId, dateType, timest],
      });
    }
  };

  // 手动触发采集模式：
  // - "current": 只采集当前视图
  // - "fill": 补齐缺失数据（有缓存就跳过）
  // - "force": 强制刷新所有数据（跳过缓存）
  const [collectMode, setCollectMode] = useState<"current" | "fill" | "force">("current");
  
  // 手动触发采集
  const triggerManualCollect = async () => {
    setTriggerLoading(true);
    try {
      const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
      
      if (collectMode === "force") {
        // 强制刷新：跳过所有缓存，从数据源重新采集
        const resp = await fetch(`${API_BASE}/panel/tasks/mengla_granular_force/run`, {
          method: "POST",
        });
        if (!resp.ok) {
          throw new Error(`强制采集启动失败: ${resp.status}`);
        }
        queryClient.invalidateQueries({ queryKey: ["mengla"] });
        alert("强制采集任务已启动！将跳过所有缓存直接从数据源采集，请在终端查看进度");
      } else if (collectMode === "fill") {
        // 补齐模式：只采集缺失的数据，有缓存就跳过
        const resp = await fetch(`${API_BASE}/panel/tasks/mengla_granular/run`, {
          method: "POST",
        });
        if (!resp.ok) {
          throw new Error(`补齐采集启动失败: ${resp.status}`);
        }
        queryClient.invalidateQueries({ queryKey: ["mengla"] });
        alert("补齐采集任务已启动！将只采集缺失的数据，已有缓存的会跳过");
      } else {
        // 当前模式：只采集当前视图
        const action = mode === "overview" ? "industryTrendRange" : mode;
        const body = mode === "overview"
          ? buildTrendQueryParams("industryTrendRange", primaryCatId, trendPeriod, trendRangeStart, trendRangeEnd)
          : buildQueryParams(action, primaryCatId, period, timest);
        
        await queryMengla({ ...body, extra: { force_refresh: true } });
        invalidateCurrent();
      }
    } catch (e) {
      console.error("手动触发采集失败", e);
      alert(`采集失败: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setTriggerLoading(false);
    }
  };

  // 采集平台可能返回 resultData 或 data；resultData 可能嵌套多层，递归解包直到无 resultData
  const pickPayload = (raw: unknown): MenglaResponseData | undefined => {
    if (!raw || typeof raw !== "object") return undefined;
    const o = raw as Record<string, unknown>;
    let payload: unknown = o.resultData ?? o.data ?? o;
    while (payload && typeof payload === "object" && "resultData" in payload) {
      const inner = (payload as Record<string, unknown>).resultData;
      if (!inner) break;
      payload = inner;
    }
    return payload as MenglaResponseData | undefined;
  };
  const trendData = pickPayload(overviewTrendQuery.data);
  const viewData = pickPayload(overviewViewQuery.data);
  const highData = pickPayload(highQuery.data);
  const hotData = pickPayload(hotQuery.data);
  const chanceData = pickPayload(chanceQuery.data);

  const trendPoints = useMemo(() => {
    if (!trendData) return [];
    const inj = trendData?.injectedVars && typeof trendData.injectedVars === "object" ? trendData.injectedVars as Record<string, unknown> : null;
    const injIr = inj?.industryTrendRange as { data?: unknown } | unknown[] | undefined;
    const raw =
      trendData?.industryTrendRange?.data ??
      (Array.isArray(trendData?.industryTrendRange) ? trendData.industryTrendRange : null) ??
      trendData?.data ??
      (injIr && typeof injIr === "object" && !Array.isArray(injIr) && "data" in injIr ? injIr.data : null) ??
      (Array.isArray(injIr) ? injIr : null) ??
      inj?.data ??
      [];
    return (Array.isArray(raw) ? raw : []) as TrendPoint[];
  }, [trendData]);

  // 兼容 industryViewV2List / industryViewV2 / 或 viewData 自身即为区间数据（无 data 嵌套）
  const industryView = useMemo((): IndustryView | null => {
    const v = viewData?.industryViewV2List ?? viewData?.industryViewV2 ?? viewData ?? null;
    if (!v || typeof v !== "object") return null;
    const vRecord = v as Record<string, unknown>;
    if ("data" in vRecord && vRecord.data) return v as IndustryView;
    if ("industrySalesRangeDtoList" in vRecord || "industryGmvRangeDtoList" in vRecord)
      return { data: v as IndustryView["data"] };
    return v as IndustryView;
  }, [viewData]);

  const highList = useMemo(() => {
    if (!highData) return [];
    const hl = highData?.highList;
    const data = hl?.data;
    // 采集可能返回 highList.data 为数组，或 highList.data.list
    const list =
      (Array.isArray(data) ? data : null) ??
      (data && typeof data === "object" && "list" in data ? (data as { list: unknown }).list : null) ??
      hl?.list ??
      highData?.list ??
      (Array.isArray(highData?.data) ? highData.data : null);
    return (Array.isArray(list) ? list : []) as HighListRow[];
  }, [highData]);

  const hotList = useMemo(() => {
    if (!hotData) return [];
    const hl = hotData?.hotList;
    const data = hl?.data;
    // 同蓝海：采集可能返回 hotList.data 为数组，或 hotList.data.list
    const list =
      (Array.isArray(data) ? data : null) ??
      (data && typeof data === "object" && "list" in data ? (data as { list: unknown }).list : null) ??
      hl?.list ??
      hotData?.list ??
      (Array.isArray(hotData?.data) ? hotData.data : null);
    return (Array.isArray(list) ? list : []) as HighListRow[];
  }, [hotData]);

  const chanceList = useMemo(() => {
    if (!chanceData) return [];
    const hl = chanceData?.chanceList;
    const data = hl?.data;
    // 同蓝海：采集可能返回 chanceList.data 为数组，或 chanceList.data.list
    const list =
      (Array.isArray(data) ? data : null) ??
      (data && typeof data === "object" && "list" in data ? (data as { list: unknown }).list : null) ??
      hl?.list ??
      chanceData?.list ??
      (Array.isArray(chanceData?.data) ? chanceData.data : null);
    return (Array.isArray(list) ? list : []) as HighListRow[];
  }, [chanceData]);

  const loading =
    mode === "overview"
      ? overviewTrendQuery.isLoading || overviewViewQuery.isLoading
      : mode === "high"
        ? highQuery.isLoading
        : mode === "hot"
          ? hotQuery.isLoading
          : chanceQuery.isLoading;

  const error =
    (mode === "overview" &&
      (overviewTrendQuery.error || overviewViewQuery.error)) ||
    (mode === "high" && highQuery.error) ||
    (mode === "hot" && hotQuery.error) ||
    (mode === "chance" && chanceQuery.error);

  // 调试：将失败原因输出到控制台，便于与后端日志对照
  if (error) {
    console.error("[MengLa] 加载萌拉数据失败", {
      mode,
      message: error instanceof Error ? error.message : String(error),
    });
  }

  const errorMessage = error ? "加载萌拉数据失败" : "";

  return (
    <div className="min-h-screen bg-[#050506] text-white relative overflow-hidden">
      <div className="pointer-events-none absolute inset-0 opacity-70">
        <div className="absolute -top-40 left-1/2 -translate-x-1/2 w-[900px] h-[900px] bg-[#5E6AD2]/25 blur-[140px]" />
        <div className="absolute -left-40 top-40 w-[600px] h-[600px] bg-fuchsia-500/15 blur-[120px]" />
        <div className="absolute -right-40 bottom-0 w-[600px] h-[600px] bg-sky-500/15 blur-[120px]" />
      </div>

      <div className="relative flex">
        <aside className="w-64 bg-black/40 border-r border-white/10 backdrop-blur-xl flex flex-col">
          <div className="px-5 py-5 border-b border-white/10">
            <div className="text-[11px] font-mono tracking-[0.25em] text-white/40 uppercase">
              MengLa
            </div>
            <div className="mt-2 flex items-center justify-between gap-2">
              <span className="text-lg font-semibold bg-gradient-to-b from-white via-white/90 to-white/60 bg-clip-text text-transparent">
                行业智能面板
              </span>
              {view !== "admin" && (
                <div className="flex items-center gap-1">
                  <select
                    value={collectMode}
                    onChange={(e) => setCollectMode(e.target.value as "current" | "fill" | "force")}
                    disabled={triggerLoading}
                    className="px-1.5 py-1 text-[10px] bg-[#0F0F12] border border-[#5E6AD2]/40 rounded text-[#5E6AD2] disabled:opacity-50 focus:outline-none"
                    title="选择采集范围"
                  >
                    <option value="current">当前</option>
                    <option value="fill">补齐</option>
                    <option value="force">全部</option>
                  </select>
                  <button
                    type="button"
                    onClick={() => triggerManualCollect()}
                    disabled={triggerLoading}
                    className="px-2 py-1 text-[10px] bg-[#5E6AD2]/20 hover:bg-[#5E6AD2]/30 border border-[#5E6AD2]/40 rounded text-[#5E6AD2] disabled:opacity-50 disabled:cursor-not-allowed transition-colors cursor-pointer"
                    title={
                      collectMode === "force" 
                        ? "强制刷新所有数据（跳过缓存）" 
                        : collectMode === "fill"
                          ? "只采集缺失的数据"
                          : "采集当前视图数据"
                    }
                  >
                    {triggerLoading ? "采集中..." : "采集"}
                  </button>
                </div>
              )}
            </div>
          </div>
          <nav className="flex-1 overflow-y-auto py-3">
            {effectiveModes.map((item) => (
              <button
                key={item.key}
                className={`w-full flex items-center justify-between px-5 py-2.5 text-xs transition-colors ${
                  view === item.key
                    ? "bg-white/10 text-white"
                    : "text-white/65 hover:bg-white/5"
                }`}
                onClick={() => setView(item.key)}
              >
                <span>{item.name}</span>
                <span className="text-[10px] font-mono tracking-[0.2em] text-white/45">
                  {item.badge}
                </span>
              </button>
            ))}
            {SHOW_ADMIN_CENTER && (
              <button
                type="button"
                className={`mt-2 w-full flex items-center justify-between px-5 py-2.5 text-xs transition-colors ${
                  view === "admin"
                    ? "bg-white/10 text-white"
                    : "text-white/65 hover:bg-white/5"
                }`}
                onClick={() => setView("admin")}
              >
                <span>管理中心</span>
                <span className="text-[10px] font-mono tracking-[0.2em] text-white/45">
                  ADMIN
                </span>
              </button>
            )}
          </nav>
        </aside>

        <main className="flex-1 min-h-0 flex flex-col px-8 py-6">
          {view === "admin" ? (
            <AdminCenterPage />
          ) : (
            <div className="space-y-6">
          <header className="flex flex-col gap-4">
            {/* 第一行：标题 + 类目选择 + 刷新 */}
            <div className="flex items-center justify-between flex-wrap gap-4">
              <div>
                <p className="text-xs font-mono tracking-[0.25em] text-white/50 uppercase">
                  DASHBOARD
                </p>
                <h1 className="mt-2 text-2xl font-semibold bg-gradient-to-b from-white via-white/90 to-white/60 bg-clip-text text-transparent">
                  {effectiveModes.find((m) => m.key === mode)?.name ?? mode}
                </h1>
                <p className="mt-1 text-[11px] text-white/55">
                  当前类目：{selectedCatLabel}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-3">
              <select
                className="bg-[#0F0F12] border border-white/10 rounded-lg px-3 py-1.5 text-xs text-white focus:outline-none focus:ring-2 focus:ring-[#5E6AD2]/50 focus:border-[#5E6AD2]"
                value={selectedCatId1 ?? ""}
                onChange={(e: ChangeEvent<HTMLSelectElement>) => {
                  const v = e.target.value || null;
                  setSelectedCatId1(v);
                  setSelectedCatId2(null);
                }}
                aria-label="一级分类"
              >
                {categories.map((cat: Category) => (
                  <option key={cat.catId} value={cat.catId}>
                    {cat.catNameCn || cat.catName}
                  </option>
                ))}
              </select>
              <select
                className="bg-[#0F0F12] border border-white/10 rounded-lg px-3 py-1.5 text-xs text-white focus:outline-none focus:ring-2 focus:ring-[#5E6AD2]/50 focus:border-[#5E6AD2]"
                value={selectedCatId2 ?? ""}
                onChange={(e: ChangeEvent<HTMLSelectElement>) =>
                  setSelectedCatId2(e.target.value || null)
                }
                aria-label="二级分类"
              >
                <option value="">全部</option>
                {level2Options.map((child: CategoryChild) => (
                  <option key={child.catId} value={child.catId}>
                    {child.catNameCn || child.catName}
                  </option>
                ))}
              </select>
              <button
                type="button"
                className="bg-[#0F0F12] border border-white/10 rounded-lg px-3 py-1.5 text-xs text-white hover:bg-white/5 focus:outline-none focus:ring-2 focus:ring-[#5E6AD2]/50 disabled:opacity-50"
                onClick={invalidateCurrent}
                disabled={loading}
              >
                刷新
              </button>
              </div>
            </div>
            {/* 第二行：非总览模式且配置允许时显示榜周期选择器 */}
            {mode !== "overview" && showRankPeriodSelector && (
              <div className="flex flex-wrap items-center gap-3 mt-2">
                <RankPeriodSelector
                  selectedPeriod={period}
                  selectedTimest={timest}
                  onPeriodChange={(p) => {
                    setPeriod(p);
                    setTimest(getDefaultTimestForPeriod(p));
                  }}
                  onTimestChange={setTimest}
                />
              </div>
            )}
          </header>

          {loading ? (
            <div className="mt-16 text-center text-sm text-white/60">
              加载中…
            </div>
          ) : errorMessage ? (
            <div className="mt-16 text-center text-sm text-red-400">
              {errorMessage}
            </div>
          ) : (
            <>
              {mode === "overview" && (
                <div className="space-y-6">
                  {/* 行业趋势：标题 + 时间选择器在趋势图旁，与区间分布并列，体现独立性 */}
                  <section className="space-y-4">
                    <header className="flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <p className="text-xs font-mono tracking-[0.2em] text-white/50 uppercase">
                          TREND
                        </p>
                        <h2 className="mt-1 text-sm font-semibold text-white">
                          行业趋势
                        </h2>
                      </div>
                      <TrendPeriodRangeSelector
                        period={trendPeriod}
                        rangeStart={trendRangeStart}
                        rangeEnd={trendRangeEnd}
                        onPeriodChange={(p) => {
                          const def = getDefaultTrendRangeForPeriod(p);
                          setTrendPeriod(p);
                          setTrendRangeStart(def.start);
                          setTrendRangeEnd(def.end);
                        }}
                        onRangeChange={(start, end) => {
                          setTrendRangeStart(start);
                          setTrendRangeEnd(end);
                        }}
                      />
                    </header>
                    <TrendChart points={trendPoints} />
                  </section>
                  <DistributionSection
                    industryView={industryView}
                    distributionPeriod={distributionPeriod}
                    distributionTimest={distributionTimest}
                    onDistributionPeriodChange={(p: PeriodType) => {
                      setDistributionPeriod(p);
                      setDistributionTimest(getDefaultTimestForPeriod(p));
                    }}
                    onDistributionTimestChange={setDistributionTimest}
                  />
                </div>
              )}
              {mode === "high" && <HotIndustryTable data={highList} />}
              {mode === "hot" && (
                <HotIndustryTable data={hotList} title="热销Top行业数据" />
              )}
              {mode === "chance" && (
                <HotIndustryTable data={chanceList} title="潜力Top行业数据" />
              )}
            </>
          )}
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
