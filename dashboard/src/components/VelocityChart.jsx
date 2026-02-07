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
  const trendColor = trend === 'up' ? '#22c55e' : trend === 'down' ? '#ef4444' : 'var(--color-textMuted)'
  const trendLabel = trend === 'up' ? 'Increasing' : trend === 'down' ? 'Decreasing' : 'Stable'

  // Format dates for display
  const chartData = daily.map(d => ({
    ...d,
    displayDate: new Date(d.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
  }))

  return (
    <div
      className="rounded-xl p-6 border"
      style={{
        backgroundColor: 'var(--color-cardBg)',
        borderColor: 'var(--color-cardBorder)'
      }}
    >
      <div className="flex items-center justify-between mb-6">
        <div>
          <h3
            className="text-lg font-semibold"
            style={{ color: 'var(--color-text)' }}
          >
            Velocity Trend
          </h3>
          <p
            className="text-sm"
            style={{ color: 'var(--color-textSecondary)' }}
          >
            Tasks completed per day
          </p>
        </div>
        <div className="flex items-center space-x-4">
          <div className="text-right">
            <p
              className="text-2xl font-bold"
              style={{ color: 'var(--color-text)' }}
            >
              {total_completed}
            </p>
            <p
              className="text-xs"
              style={{ color: 'var(--color-textSecondary)' }}
            >
              Total (14 days)
            </p>
          </div>
          <div className="text-right">
            <p
              className="text-2xl font-bold"
              style={{ color: 'var(--color-accent)' }}
            >
              {weekly_avg}
            </p>
            <p
              className="text-xs"
              style={{ color: 'var(--color-textSecondary)' }}
            >
              Weekly avg
            </p>
          </div>
          <div className="flex items-center space-x-1" style={{ color: trendColor }}>
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
                <stop offset="5%" stopColor="var(--color-accent)" stopOpacity={0.3} />
                <stop offset="95%" stopColor="var(--color-accent)" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
            <XAxis
              dataKey="displayDate"
              stroke="var(--color-textMuted)"
              tick={{ fill: 'var(--color-textMuted)', fontSize: 12 }}
              tickLine={false}
            />
            <YAxis
              stroke="var(--color-textMuted)"
              tick={{ fill: 'var(--color-textMuted)', fontSize: 12 }}
              tickLine={false}
              axisLine={false}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: 'var(--color-cardBg)',
                border: '1px solid var(--color-border)',
                borderRadius: '8px',
                color: 'var(--color-text)',
              }}
              labelStyle={{ color: 'var(--color-textSecondary)' }}
            />
            <Area
              type="monotone"
              dataKey="count"
              stroke="var(--color-accent)"
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
