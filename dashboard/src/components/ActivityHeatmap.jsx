import React from 'react'

const DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
const HOURS = Array.from({ length: 24 }, (_, i) => i)

function getIntensityColor(count, maxCount) {
  if (count === 0) return 'bg-gray-800'
  const intensity = Math.min(count / Math.max(maxCount, 1), 1)
  if (intensity < 0.25) return 'bg-green-900'
  if (intensity < 0.5) return 'bg-green-700'
  if (intensity < 0.75) return 'bg-green-500'
  return 'bg-green-400'
}

function ActivityHeatmap({ data }) {
  if (!data || data.length === 0) return null

  // Create a lookup map
  const activityMap = new Map()
  let maxCount = 0

  for (const item of data) {
    const key = `${item.day}-${item.hour}`
    activityMap.set(key, item.count)
    if (item.count > maxCount) maxCount = item.count
  }

  return (
    <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
      <div className="mb-6">
        <h3 className="text-lg font-semibold text-white">Activity Heatmap</h3>
        <p className="text-sm text-gray-400">Task completions by day and hour</p>
      </div>

      <div className="overflow-x-auto">
        <div className="min-w-[800px]">
          {/* Hour labels */}
          <div className="flex mb-1">
            <div className="w-20 flex-shrink-0" />
            {HOURS.filter(h => h % 3 === 0).map((hour) => (
              <div
                key={hour}
                className="text-xs text-gray-500 text-center"
                style={{ width: `${100 / 8}%` }}
              >
                {hour.toString().padStart(2, '0')}:00
              </div>
            ))}
          </div>

          {/* Heatmap grid */}
          {DAYS.map((day) => (
            <div key={day} className="flex items-center mb-1">
              <div className="w-20 flex-shrink-0 text-xs text-gray-400 pr-2">{day.slice(0, 3)}</div>
              <div className="flex-1 flex gap-0.5">
                {HOURS.map((hour) => {
                  const count = activityMap.get(`${day}-${hour}`) || 0
                  return (
                    <div
                      key={hour}
                      className={`flex-1 h-4 rounded-sm ${getIntensityColor(count, maxCount)} transition-colors hover:ring-1 hover:ring-white`}
                      title={`${day} ${hour}:00 - ${count} tasks`}
                    />
                  )
                })}
              </div>
            </div>
          ))}

          {/* Legend */}
          <div className="flex items-center justify-end mt-4 space-x-2">
            <span className="text-xs text-gray-500">Less</span>
            <div className="flex space-x-1">
              <div className="w-4 h-4 rounded-sm bg-gray-800" />
              <div className="w-4 h-4 rounded-sm bg-green-900" />
              <div className="w-4 h-4 rounded-sm bg-green-700" />
              <div className="w-4 h-4 rounded-sm bg-green-500" />
              <div className="w-4 h-4 rounded-sm bg-green-400" />
            </div>
            <span className="text-xs text-gray-500">More</span>
          </div>
        </div>
      </div>
    </div>
  )
}

export default ActivityHeatmap
