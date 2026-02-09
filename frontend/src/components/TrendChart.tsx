import React from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import type { TrendPoint } from "../types/mengla";
import { ChartSkeleton, InlineError } from "./LoadingSkeleton";
import { Card, CardHeader, CardTitle, CardContent } from "./ui/card";

interface TrendChartProps {
  points: TrendPoint[];
  isLoading?: boolean;
  error?: Error | null;
  onRetry?: () => void;
}

export const TrendChart = React.memo(function TrendChart({ points, isLoading, error, onRetry }: TrendChartProps) {
  if (isLoading) return <ChartSkeleton />;

  const data =
    points?.map((p) => ({
      date: p.timest,
      productCount: p.salesSkuCount,
      dailySales: p.monthSales,
      dailyRevenue: p.monthGmv,
      avgPrice: p.currentDayPrice,
    })) ?? [];

  return (
    <Card>
      <CardHeader>
        <p className="text-xs font-mono tracking-[0.2em] text-muted-foreground uppercase">
          TREND
        </p>
        <CardTitle>
          行业趋势（销量 &amp; GMV）
        </CardTitle>
      </CardHeader>
      <CardContent>
        {error ? (
          <InlineError message="加载趋势数据失败" onRetry={onRetry} />
        ) : (
        <div className="h-80">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data}>
              <CartesianGrid stroke="#ffffff14" strokeDasharray="3 3" />
              <XAxis
                dataKey="date"
                tick={{ fill: "rgba(255,255,255,0.45)", fontSize: 10 }}
              />
              <YAxis
                tick={{ fill: "rgba(255,255,255,0.45)", fontSize: 10 }}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#050506",
                  border: "1px solid rgba(255,255,255,0.12)",
                  borderRadius: 12,
                  padding: 8,
                  color: "#EDEDEF",
                  fontSize: 11,
                }}
              />
              <Legend
                wrapperStyle={{ fontSize: 11, color: "rgba(255,255,255,0.6)" }}
              />
              <Line
                type="monotone"
                dataKey="dailySales"
                name="月销量"
                stroke="#60a5fa"
                strokeWidth={1.8}
                dot={false}
              />
              <Line
                type="monotone"
                dataKey="dailyRevenue"
                name="月GMV"
                stroke="#a855f7"
                strokeWidth={1.8}
                dot={false}
              />
              <Line
                type="monotone"
                dataKey="productCount"
                name="有销量商品数"
                stroke="#22c55e"
                strokeWidth={1.4}
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
        )}
      </CardContent>
    </Card>
  );
});
