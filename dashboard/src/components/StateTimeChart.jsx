import React from 'react'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'

const STATE_COLORS = {
  Todo: '#8B5CF6',
  'In Progress': '#F59E0B',
  Done: '#22C55E',
}

function StateTimeChart({ data }) {
  if (!data) return null

  const chartData = Object.entries(data)
    .filter(([state]) => state !== 'Done') // Don't show Done since it's 0
    .map(([state, hours]) => ({
      state,
      hours: Number(hours.toFixed(2)),
      fill: STATE_COLORS[state] || '#6B7280',
    }))

  return (
    <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
      <div className="mb-6">
        <h3 className="text-lg font-semibold text-white">Время в статусе</h3>
        <p className="text-sm text-gray-400">Среднее количество часов на переход</p>
      </div>

      <div className="h-48">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData} layout="vertical">
            <CartesianGrid strokeDasharray="3 3" stroke="#374151" horizontal={false} />
            <XAxis
              type="number"
              stroke="#9CA3AF"
              tick={{ fill: '#9CA3AF', fontSize: 12 }}
              tickLine={false}
              axisLine={false}
              unit="h"
            />
            <YAxis
              type="category"
              dataKey="state"
              stroke="#9CA3AF"
              tick={{ fill: '#9CA3AF', fontSize: 12 }}
              tickLine={false}
              axisLine={false}
              width={80}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: '#1F2937',
                border: '1px solid #374151',
                borderRadius: '8px',
                color: '#F9FAFB',
              }}
              formatter={(value) => [`${value} часов`, 'Среднее время']}
              cursor={{ fill: 'rgba(59, 130, 246, 0.1)' }}
            />
            <Bar dataKey="hours" radius={[0, 4, 4, 0]}>
              {chartData.map((entry, index) => (
                <rect key={`bar-${index}`} fill={entry.fill} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* State Legend */}
      <div className="flex items-center justify-center space-x-6 mt-4">
        {Object.entries(STATE_COLORS).map(([state, color]) => (
          <div key={state} className="flex items-center space-x-2">
            <div className="w-3 h-3 rounded" style={{ backgroundColor: color }} />
            <span className="text-sm text-gray-400">{state}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export default StateTimeChart
