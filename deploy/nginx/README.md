# Nginx Configuration for MCP Servers

## Quick Start

### 1. Install Nginx

```bash
apt update && apt install -y nginx certbot python3-certbot-nginx
```

### 2. Configure

```bash
# Copy config
cp mcp-servers.conf /etc/nginx/sites-available/

# Edit domain name
sed -i 's/mcp.yourdomain.com/YOUR_ACTUAL_DOMAIN/g' /etc/nginx/sites-available/mcp-servers.conf

# Enable site
ln -sf /etc/nginx/sites-available/mcp-servers.conf /etc/nginx/sites-enabled/

# Remove default site (optional)
rm -f /etc/nginx/sites-enabled/default

# Test config
nginx -t
```

### 3. SSL Certificate

```bash
# Get certificate (will auto-configure nginx)
certbot --nginx -d YOUR_ACTUAL_DOMAIN

# Auto-renewal (usually automatic, but verify)
systemctl enable certbot.timer
```

### 4. Start

```bash
systemctl reload nginx
```

## Endpoints

After setup, your MCP servers will be available at:

| Service | URL |
|---------|-----|
| Task MCP | `https://YOUR_DOMAIN/task/sse` |
| Telegram MCP | `https://YOUR_DOMAIN/telegram/sse` |
| Task Health | `https://YOUR_DOMAIN/task/health` |
| Telegram Health | `https://YOUR_DOMAIN/telegram/health` |

## Client Configuration

Update your `mcp_config.py`:

```python
TASK_MCP_URL = "https://YOUR_DOMAIN/task/sse"
TELEGRAM_MCP_URL = "https://YOUR_DOMAIN/telegram/sse"
```

## Optional: Basic Auth

For additional security:

```bash
# Create password file
apt install -y apache2-utils
htpasswd -c /etc/nginx/.htpasswd mcp_user

# Uncomment auth lines in mcp-servers.conf
# auth_basic "MCP Servers";
# auth_basic_user_file /etc/nginx/.htpasswd;

nginx -t && systemctl reload nginx
```

## Troubleshooting

### Check logs
```bash
tail -f /var/log/nginx/error.log
tail -f /var/log/nginx/access.log
```

### Test SSE connection
```bash
curl -N https://YOUR_DOMAIN/task/sse
```

### Verify upstream is running
```bash
curl http://127.0.0.1:6001/health
curl http://127.0.0.1:6002/health
```
