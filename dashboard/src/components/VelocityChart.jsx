import React from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Area,
  AreaChart,
} from 'recharts'
import { TrendingUp, TrendingDown, Minus } from 'lucide-react'

function VelocityChart({ data }) {
  if (!data) return null

  const { daily, weekly_avg, trend, total_completed } = data

  const TrendIcon = trend === 'up' ? TrendingUp : trend === 'down' ? TrendingDown : Minus
  const trendColor = trend === 'up' ? 'text-green-500' : trend === 'down' ? 'text-red-500' : 'text-gray-400'
  const trendLabel = trend === 'up' ? 'Increasing' : trend === 'down' ? 'Decreasing' : 'Stable'

  // Format dates for display
  const chartData = daily.map(d => ({
    ...d,
    displayDate: new Date(d.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
  }))

  return (
    <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h3 className="text-lg font-semibold text-white">Velocity Trend</h3>
          <p className="text-sm text-gray-400">Tasks completed per day</p>
        </div>
        <div className="flex items-center space-x-4">
          <div className="text-right">
            <p className="text-2xl font-bold text-white">{total_completed}</p>
            <p className="text-xs text-gray-400">Total (14 days)</p>
          </div>
          <div className="text-right">
            <p className="text-2xl font-bold text-blue-400">{weekly_avg}</p>
            <p className="text-xs text-gray-400">Weekly avg</p>
          </div>
          <div className={`flex items-center space-x-1 ${trendColor}`}>
            <TrendIcon className="w-5 h-5" />
            <span className="text-sm font-medium">{trendLabel}</span>
          </div>
        </div>
      </div>

      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData}>
            <defs>
              <linearGradient id="colorVelocity" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#3B82F6" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#3B82F6" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
            <XAxis
              dataKey="displayDate"
              stroke="#9CA3AF"
              tick={{ fill: '#9CA3AF', fontSize: 12 }}
              tickLine={false}
            />
            <YAxis
              stroke="#9CA3AF"
              tick={{ fill: '#9CA3AF', fontSize: 12 }}
              tickLine={false}
              axisLine={false}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: '#1F2937',
                border: '1px solid #374151',
                borderRadius: '8px',
                color: '#F9FAFB',
              }}
              labelStyle={{ color: '#9CA3AF' }}
            />
            <Area
              type="monotone"
              dataKey="count"
              stroke="#3B82F6"
              strokeWidth={2}
              fill="url(#colorVelocity)"
              name="Tasks Completed"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

export default VelocityChart
