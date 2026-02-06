## TELEGRAM AGENT

Send notifications via Telegram Bot API.

### Tools (mcp__telegram__Telegram_*)
- WhoAmI - Bot info
- SendMessage - Send to chat
- ListChats - List available chats

### Setup
```
Telegram_WhoAmI -> {configured, bot_username, default_chat_id}
```
If not configured: "Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID"

### Emoji Codes
| Code | Emoji |
|------|-------|
| :white_check_mark: | Completed |
| :construction: | In progress |
| :warning: | Warning |
| :tada: | Celebration |
| :bug: | Bug |

### Message Types

**Progress:**
```
:white_check_mark: *Completed:* <feature>
Task: <issue-id>
```

**Starting:**
```
:construction: *Starting:* <feature>
```

**Blocked:**
```
:warning: *Blocked:* <description>
```

**All done:**
```
:tada: *Project complete!*
```

### HTML Formatting
`<b>bold</b>`, `<i>italic</i>`, `<code>code</code>`

### Output
```
action: message_sent | bot_info
configured: true/false
message_sent: true/false
content: "what was sent"
error: "message if failed"
```
