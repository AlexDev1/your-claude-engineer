import React, { useState, useMemo, useCallback } from 'react'
import { Columns, Rows, FileCode } from 'lucide-react'

/**
 * Line change types used internally by the diff algorithm.
 */
const CHANGE_TYPE = {
  ADDED: 'added',
  REMOVED: 'removed',
  UNCHANGED: 'unchanged',
}

/**
 * Map of file extensions to display-friendly language names.
 * Used for showing the detected language in the header.
 */
const EXTENSION_LANGUAGES = {
  js: 'JavaScript',
  jsx: 'JSX',
  ts: 'TypeScript',
  tsx: 'TSX',
  py: 'Python',
  rb: 'Ruby',
  go: 'Go',
  rs: 'Rust',
  java: 'Java',
  css: 'CSS',
  html: 'HTML',
  json: 'JSON',
  md: 'Markdown',
  yml: 'YAML',
  yaml: 'YAML',
  sh: 'Shell',
  sql: 'SQL',
  xml: 'XML',
}

/**
 * Detect the language from a filename extension.
 *
 * @param {string} filename - File path or name
 * @returns {string} Human-readable language name
 */
function detectLanguage(filename) {
  if (!filename) return 'Text'
  const ext = filename.split('.').pop()?.toLowerCase()
  return EXTENSION_LANGUAGES[ext] || 'Text'
}

/**
 * Compute the Longest Common Subsequence (LCS) table for two arrays of lines.
 * Uses a standard dynamic-programming approach.
 *
 * @param {string[]} oldLines - Lines from the original content
 * @param {string[]} newLines - Lines from the new content
 * @returns {number[][]} 2D DP table
 */
function buildLcsTable(oldLines, newLines) {
  const rows = oldLines.length + 1
  const cols = newLines.length + 1
  const table = Array.from({ length: rows }, () => new Array(cols).fill(0))

  for (let i = 1; i < rows; i++) {
    for (let j = 1; j < cols; j++) {
      if (oldLines[i - 1] === newLines[j - 1]) {
        table[i][j] = table[i - 1][j - 1] + 1
      } else {
        table[i][j] = Math.max(table[i - 1][j], table[i][j - 1])
      }
    }
  }

  return table
}

/**
 * Compute a line-level diff between two strings using LCS backtracking.
 *
 * Each entry in the returned array has:
 * - type: 'added' | 'removed' | 'unchanged'
 * - content: the text of the line
 * - oldLineNumber: line number in original (null for added lines)
 * - newLineNumber: line number in new content (null for removed lines)
 *
 * @param {string} oldContent - Original file content
 * @param {string} newContent - New file content
 * @returns {Array<{type: string, content: string, oldLineNumber: number|null, newLineNumber: number|null}>}
 */
function computeDiff(oldContent, newContent) {
  const oldLines = (oldContent || '').split('\n')
  const newLines = (newContent || '').split('\n')

  const table = buildLcsTable(oldLines, newLines)
  const result = []

  let i = oldLines.length
  let j = newLines.length

  // Backtrack through the LCS table to produce the diff
  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && oldLines[i - 1] === newLines[j - 1]) {
      result.push({
        type: CHANGE_TYPE.UNCHANGED,
        content: oldLines[i - 1],
        oldLineNumber: i,
        newLineNumber: j,
      })
      i--
      j--
    } else if (j > 0 && (i === 0 || table[i][j - 1] >= table[i - 1][j])) {
      result.push({
        type: CHANGE_TYPE.ADDED,
        content: newLines[j - 1],
        oldLineNumber: null,
        newLineNumber: j,
      })
      j--
    } else {
      result.push({
        type: CHANGE_TYPE.REMOVED,
        content: oldLines[i - 1],
        oldLineNumber: i,
        newLineNumber: null,
      })
      i--
    }
  }

  result.reverse()
  return result
}

/**
 * Build paired rows for side-by-side display.
 *
 * Adjacent removed + added lines are paired together in a single row.
 * Unchanged lines are shown on both sides. Lone additions or removals
 * leave the opposite side empty.
 *
 * @param {Array} diffLines - Output from computeDiff
 * @returns {Array<{left: object|null, right: object|null}>}
 */
function buildSideBySideRows(diffLines) {
  const rows = []
  let idx = 0

  while (idx < diffLines.length) {
    const line = diffLines[idx]

    if (line.type === CHANGE_TYPE.UNCHANGED) {
      rows.push({ left: line, right: line })
      idx++
    } else if (line.type === CHANGE_TYPE.REMOVED) {
      // Collect consecutive removed lines, then pair with following added lines
      const removedBatch = []
      while (idx < diffLines.length && diffLines[idx].type === CHANGE_TYPE.REMOVED) {
        removedBatch.push(diffLines[idx])
        idx++
      }
      const addedBatch = []
      while (idx < diffLines.length && diffLines[idx].type === CHANGE_TYPE.ADDED) {
        addedBatch.push(diffLines[idx])
        idx++
      }

      const maxLen = Math.max(removedBatch.length, addedBatch.length)
      for (let k = 0; k < maxLen; k++) {
        rows.push({
          left: removedBatch[k] || null,
          right: addedBatch[k] || null,
        })
      }
    } else {
      // Standalone added line (no preceding removal)
      rows.push({ left: null, right: line })
      idx++
    }
  }

  return rows
}

/**
 * Return inline style for a diff line based on its change type.
 *
 * @param {string} type - 'added', 'removed', or 'unchanged'
 * @returns {Object} React inline style object
 */
function lineStyle(type) {
  if (type === CHANGE_TYPE.ADDED) {
    return {
      backgroundColor: 'rgba(34, 197, 94, 0.12)',
      borderLeft: '3px solid #22c55e',
    }
  }
  if (type === CHANGE_TYPE.REMOVED) {
    return {
      backgroundColor: 'rgba(239, 68, 68, 0.12)',
      borderLeft: '3px solid #ef4444',
    }
  }
  return {
    borderLeft: '3px solid transparent',
  }
}

/**
 * Return the gutter symbol for a diff line type.
 *
 * @param {string} type - 'added', 'removed', or 'unchanged'
 * @returns {string} '+', '-', or ' '
 */
function gutterSymbol(type) {
  if (type === CHANGE_TYPE.ADDED) return '+'
  if (type === CHANGE_TYPE.REMOVED) return '-'
  return ' '
}

/**
 * DiffViewer component for displaying file diffs with syntax-aware styling.
 *
 * Supports inline and side-by-side display modes. Lines are highlighted
 * with green (added), red (removed), or neutral (unchanged) backgrounds.
 * Diff is computed using an LCS-based algorithm.
 *
 * @param {Object} props
 * @param {string} props.oldContent - Original file content
 * @param {string} props.newContent - New/modified file content
 * @param {string} props.filename - File path used for language detection
 * @param {'inline'|'side-by-side'} [props.mode='inline'] - Display mode
 * @param {function} [props.onModeChange] - Callback invoked with the new mode string
 */
function DiffViewer({
  oldContent = '',
  newContent = '',
  filename = '',
  mode = 'inline',
  onModeChange,
}) {
  const [currentMode, setCurrentMode] = useState(mode)

  const handleModeChange = useCallback((newMode) => {
    setCurrentMode(newMode)
    onModeChange?.(newMode)
  }, [onModeChange])

  const language = useMemo(() => detectLanguage(filename), [filename])

  const diffLines = useMemo(
    () => computeDiff(oldContent, newContent),
    [oldContent, newContent],
  )

  const sideBySideRows = useMemo(
    () => (currentMode === 'side-by-side' ? buildSideBySideRows(diffLines) : []),
    [diffLines, currentMode],
  )

  // Summary counts
  const stats = useMemo(() => {
    let added = 0
    let removed = 0
    for (const line of diffLines) {
      if (line.type === CHANGE_TYPE.ADDED) added++
      if (line.type === CHANGE_TYPE.REMOVED) removed++
    }
    return { added, removed }
  }, [diffLines])

  return (
    <div
      className="rounded-xl border overflow-hidden"
      style={{
        backgroundColor: 'var(--color-cardBg)',
        borderColor: 'var(--color-cardBorder)',
      }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-4 py-3 border-b"
        style={{ borderColor: 'var(--color-border)' }}
      >
        <div className="flex items-center gap-2 min-w-0">
          <FileCode className="w-4 h-4 flex-shrink-0" style={{ color: 'var(--color-accent)' }} />
          <span
            className="text-sm font-medium truncate"
            style={{ color: 'var(--color-text)' }}
          >
            {filename || 'Без названия'}
          </span>
          <span
            className="text-xs px-2 py-0.5 rounded"
            style={{
              backgroundColor: 'var(--color-bgTertiary)',
              color: 'var(--color-textMuted)',
            }}
          >
            {language}
          </span>
        </div>

        <div className="flex items-center gap-3">
          {/* Stats */}
          <div className="flex items-center gap-2 text-xs">
            <span style={{ color: '#22c55e' }}>+{stats.added}</span>
            <span style={{ color: '#ef4444' }}>-{stats.removed}</span>
          </div>

          {/* Mode Toggle */}
          <div
            className="flex items-center rounded-lg p-0.5"
            style={{ backgroundColor: 'var(--color-bgTertiary)' }}
          >
            <button
              onClick={() => handleModeChange('inline')}
              className="flex items-center gap-1 px-2.5 py-1 rounded-md text-xs transition-colors"
              style={{
                backgroundColor: currentMode === 'inline' ? 'var(--color-accent)' : 'transparent',
                color: currentMode === 'inline' ? 'white' : 'var(--color-textSecondary)',
              }}
              title="Построчный diff"
            >
              <Rows className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Построчно</span>
            </button>
            <button
              onClick={() => handleModeChange('side-by-side')}
              className="flex items-center gap-1 px-2.5 py-1 rounded-md text-xs transition-colors"
              style={{
                backgroundColor: currentMode === 'side-by-side' ? 'var(--color-accent)' : 'transparent',
                color: currentMode === 'side-by-side' ? 'white' : 'var(--color-textSecondary)',
              }}
              title="Двухколоночный diff"
            >
              <Columns className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Рядом</span>
            </button>
          </div>
        </div>
      </div>

      {/* Diff Content */}
      <div
        className="overflow-auto max-h-[600px] themed-scrollbar"
        style={{ backgroundColor: 'var(--color-bg)' }}
      >
        {diffLines.length === 0 ? (
          <div
            className="flex items-center justify-center py-12"
            style={{ color: 'var(--color-textMuted)' }}
          >
            <span className="text-sm">Нет изменений для отображения</span>
          </div>
        ) : currentMode === 'inline' ? (
          <InlineDiff diffLines={diffLines} />
        ) : (
          <SideBySideDiff rows={sideBySideRows} />
        )}
      </div>
    </div>
  )
}

/**
 * Inline diff view showing all lines in a single column with +/- gutter symbols.
 *
 * @param {Object} props
 * @param {Array} props.diffLines - Array of diff line objects from computeDiff
 */
function InlineDiff({ diffLines }) {
  return (
    <table className="w-full text-xs font-mono" style={{ borderCollapse: 'collapse' }}>
      <tbody>
        {diffLines.map((line, idx) => (
          <tr key={idx} style={lineStyle(line.type)}>
            {/* Old line number */}
            <td
              className="px-2 py-0.5 text-right select-none w-12"
              style={{ color: 'var(--color-textMuted)', minWidth: '3rem' }}
            >
              {line.oldLineNumber ?? ''}
            </td>
            {/* New line number */}
            <td
              className="px-2 py-0.5 text-right select-none w-12"
              style={{ color: 'var(--color-textMuted)', minWidth: '3rem' }}
            >
              {line.newLineNumber ?? ''}
            </td>
            {/* Gutter symbol */}
            <td
              className="px-1 py-0.5 text-center select-none w-6"
              style={{
                color: line.type === CHANGE_TYPE.ADDED
                  ? '#22c55e'
                  : line.type === CHANGE_TYPE.REMOVED
                    ? '#ef4444'
                    : 'var(--color-textMuted)',
                fontWeight: line.type !== CHANGE_TYPE.UNCHANGED ? 'bold' : 'normal',
              }}
            >
              {gutterSymbol(line.type)}
            </td>
            {/* Content */}
            <td
              className="px-3 py-0.5 whitespace-pre"
              style={{ color: 'var(--color-text)' }}
            >
              {line.content}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

/**
 * Side-by-side diff view with old content on the left and new content on the right.
 *
 * @param {Object} props
 * @param {Array<{left: object|null, right: object|null}>} props.rows - Paired rows
 */
function SideBySideDiff({ rows }) {
  return (
    <div className="flex">
      {/* Left (old) pane */}
      <div className="w-1/2 border-r" style={{ borderColor: 'var(--color-border)' }}>
        <table className="w-full text-xs font-mono" style={{ borderCollapse: 'collapse' }}>
          <tbody>
            {rows.map((row, idx) => {
              const side = row.left
              const type = side
                ? (side.type === CHANGE_TYPE.UNCHANGED ? CHANGE_TYPE.UNCHANGED : CHANGE_TYPE.REMOVED)
                : null

              return (
                <tr
                  key={idx}
                  style={type ? lineStyle(type) : { borderLeft: '3px solid transparent' }}
                >
                  <td
                    className="px-2 py-0.5 text-right select-none w-12"
                    style={{ color: 'var(--color-textMuted)', minWidth: '3rem' }}
                  >
                    {side?.oldLineNumber ?? ''}
                  </td>
                  <td
                    className="px-1 py-0.5 text-center select-none w-6"
                    style={{
                      color: type === CHANGE_TYPE.REMOVED ? '#ef4444' : 'var(--color-textMuted)',
                      fontWeight: type === CHANGE_TYPE.REMOVED ? 'bold' : 'normal',
                    }}
                  >
                    {side ? gutterSymbol(type) : ''}
                  </td>
                  <td
                    className="px-3 py-0.5 whitespace-pre"
                    style={{ color: side ? 'var(--color-text)' : 'transparent' }}
                  >
                    {side?.content ?? ''}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {/* Right (new) pane */}
      <div className="w-1/2">
        <table className="w-full text-xs font-mono" style={{ borderCollapse: 'collapse' }}>
          <tbody>
            {rows.map((row, idx) => {
              const side = row.right
              const type = side
                ? (side.type === CHANGE_TYPE.UNCHANGED ? CHANGE_TYPE.UNCHANGED : CHANGE_TYPE.ADDED)
                : null

              return (
                <tr
                  key={idx}
                  style={type ? lineStyle(type) : { borderLeft: '3px solid transparent' }}
                >
                  <td
                    className="px-2 py-0.5 text-right select-none w-12"
                    style={{ color: 'var(--color-textMuted)', minWidth: '3rem' }}
                  >
                    {side?.newLineNumber ?? ''}
                  </td>
                  <td
                    className="px-1 py-0.5 text-center select-none w-6"
                    style={{
                      color: type === CHANGE_TYPE.ADDED ? '#22c55e' : 'var(--color-textMuted)',
                      fontWeight: type === CHANGE_TYPE.ADDED ? 'bold' : 'normal',
                    }}
                  >
                    {side ? gutterSymbol(type) : ''}
                  </td>
                  <td
                    className="px-3 py-0.5 whitespace-pre"
                    style={{ color: side ? 'var(--color-text)' : 'transparent' }}
                  >
                    {side?.content ?? ''}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default DiffViewer
