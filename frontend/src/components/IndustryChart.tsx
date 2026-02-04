import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

interface ChartDataPoint {
  date: string;
  value?: number;
  [key: string]: unknown;
}

interface IndustryChartProps {
  data: ChartDataPoint[];
}

export default function IndustryChart({ data }: IndustryChartProps) {
  return (
    <div className="h-96 w-full bg-white p-4 rounded-lg shadow">
      <h2 className="text-xl font-bold mb-4">行业趋势分析</h2>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="date" />
          <YAxis />
          <Tooltip />
          <Line type="monotone" dataKey="value" stroke="#6366f1" strokeWidth={2} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
