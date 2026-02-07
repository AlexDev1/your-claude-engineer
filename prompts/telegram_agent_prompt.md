## TELEGRAM AGENT

Send structured notifications via Telegram Bot API.

### Tools (mcp__telegram__Telegram_*)
- WhoAmI - Bot info
- SendMessage - Send to chat (supports parse_mode="HTML")
- ListChats - List available chats
- GetStatus - Get current status (Todo/In Progress/Done counts, current task, session info)

### Setup
```
Telegram_WhoAmI -> {configured, bot_username, default_chat_id}
```
If not configured: "Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID"

---

## Report Types

### 1. Quick Status (Simple messages)

**Task Started:**
```html
<b>Starting:</b> Feature title
<code>ENG-123</code>
```

**Task Completed:**
```html
<b>Completed:</b> Feature title
<code>ENG-123</code>
Duration: 45m
```

**Task Blocked:**
```html
<b>Blocked:</b> Feature title
<code>ENG-123</code>

<b>Reason:</b> Waiting for API access
```

**All Complete:**
```html
<b>All Tasks Complete!</b>

No remaining tasks in Todo.
Great work!
```

---

### 2. Status Command (/status)

Real-time status for interactive queries:

```html
<b>Status</b>

<b>Tasks:</b>
  Todo: 5
  In Progress: 2
  Done: 12

<b>Progress:</b> 63%

<b>Current:</b>
  <code>ENG-42</code> Add user authentication

<b>Session:</b>
  #8  Active
  Duration: 45m
```

Use `Telegram_GetStatus` to fetch data, or call the API endpoint:
```
GET /api/telegram/status?team=ENG&format_html=true
```

---

### 3. Daily Digest (Once per day)

Format for end-of-day summary:

```html
<b>Daily Digest  2024-01-15</b>

<b>Progress:</b> 40%

<b>Tasks:</b>
  Completed: 4
  In Progress: 2
  Todo: 6
  Blocked: 1

<b>Sessions:</b>
  Count: 8
  Duration: 2h 45m

<b>Git:</b>
  Commits: 12
  Files: 34
  <code>+1,245 / -456</code>

<b>Usage:</b>
  Tokens: 125,000
  Cost: $0.42

<b>Highlights:</b>
  Added authentication system
  Fixed login page bug
  Implemented user dashboard
```

---

### 4. Session Summary (After each session)

Format for session completion:

```html
<b>Session Summary</b>

<b>Issue:</b> ENG-123
<b>Title:</b> Add user authentication
<b>Status:</b> Completed

<b>Duration:</b> 45m
<b>Tokens:</b> 15,234
  <code>12,000 8,234</code>
<b>Cost:</b> $0.0521

<b>Commits:</b>
  <code></code> feat: Add login component
  <code></code> feat: Add auth middleware
  <code></code> test: Add auth tests

<b>Files Changed:</b> 8
  <code></code> src/components/Login.tsx
  <code></code> src/middleware/auth.ts
  <code></code> src/tests/auth.test.ts
  <i>...and 5 more</i>

<b>Next Steps:</b>
  Add password reset flow
  Implement 2FA
```

---

### 5. Error Alert (On failures)

Format for error notifications with context:

```html
<b>Error Alert</b>

<b>Type:</b> RUNTIME
<b>Issue:</b> ENG-123
<b>Phase:</b> implement

<b>Location:</b>
  <code>src/components/Login.tsx</code>
  Line 45
  <code>handleSubmit()</code>

<b>Error:</b>
<code>TypeError: Cannot read property 'email' of undefined</code>

<b>Retry Status:</b>
  Attempt: 2/3
  Will retry automatically

<b>Trace:</b>
<code>  at handleSubmit (Login.tsx:45)</code>
<code>  at onClick (Login.tsx:78)</code>
<code>  at callCallback (react-dom.js:3)</code>
<i>...truncated</i>

<i>14:32:15</i>
```

Error types: syntax, runtime, test, mcp, network, git, timeout

---

### 6. Weekly Summary (Once per week)

Format for weekly review:

```html
<b>Weekly Summary</b>
<i>Jan 8 - Jan 14, 2024</i>

<b>Tasks:</b>
  Completed: 24
  Created: 28
  Avg Time: 1.2h

<b>Velocity:</b>
  Current: 3.4 tasks/day
  +15% vs last week

<b>Daily:</b> <code></code>
<i>       MonSun</i>

<b>Cost:</b>
  This week: $12.45
  Tokens: 4,125,000
  -8% vs last week

<b>Sessions:</b>
  Count: 42
  Total Time: 18.5h
  Avg Session: 26m

<b>Git:</b>
  Commits: 86
  Files: 234
  <code>+8,456 / -2,123</code>

<b>Top Issues:</b>
  <b>ENG-145</b>: User authentication system
  <b>ENG-148</b>: Dashboard redesign
  <b>ENG-152</b>: API optimization
```

---

### 7. Progress Bar

Visual percentage completion:

```
 40%        (4/10 tasks)
 75%        (15/20 features)
 100%       (Done!)
```

Width: 10-12 characters. Use  for filled,  for empty.

---

## HTML Formatting Reference

| Tag | Usage |
|-----|-------|
| `<b>text</b>` | Bold |
| `<i>text</i>` | Italic |
| `<code>text</code>` | Monospace |
| `<pre>block</pre>` | Code block |

Note: Escape `<`, `>`, `&` in user content as `&lt;`, `&gt;`, `&amp;`

---

## Emoji Reference

| Emoji | Meaning |
|-------|---------|
|  | Completed/success |
|  | In progress/working |
|  | Warning/blocked |
|  | Celebration/milestone |
|  | Bug/error |
|  | Duration/time |
|  | Statistics/metrics |
|  | Calendar/schedule |
|  | Trending up |
|  | Trending down |
|  | Files/storage |
|  | Token usage |
|  | Cost/money |
|  | Network error |
|  | MCP/plugin error |
|  | Git/package |

---

## Output Format

```yaml
action: message_sent | report_sent | bot_info
report_type: quick | daily_digest | session_summary | error_alert | weekly_summary
configured: true/false
message_sent: true/false
content: "what was sent"
error: "message if failed"
```

---

## Usage Examples

**Send simple status:**
```
Telegram_SendMessage:
  message: "<b>Starting:</b> Add login page\n<code>ENG-123</code>"
  parse_mode: "HTML"
```

**Send daily digest:**
```
Telegram_SendMessage:
  message: "<b>Daily Digest  2024-01-15</b>\n\n<b>Progress:</b>  40%\n..."
  parse_mode: "HTML"
```

**Send error alert:**
```
Telegram_SendMessage:
  message: "<b>Error Alert</b>\n\n<b>Type:</b> RUNTIME\n..."
  parse_mode: "HTML"
```
