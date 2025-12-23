# 502 Bad Gateway Error - Troubleshooting Guide

## Problem
You're getting a **502 Bad Gateway** error when making requests to `https://capi.skintruth.in`. This means nginx can't reach the FastAPI backend server.

## Quick Fix Steps

### 1. Check if the FastAPI service is running

```bash
# Check service status
sudo systemctl status chatbot

# If it's not running, start it
sudo systemctl start chatbot

# If it's failed, check the logs
sudo journalctl -u chatbot -n 100 --no-pager
```

### 2. Verify the service is listening on port 8888

```bash
# Check if port 8888 is in use
sudo netstat -tlnp | grep 8888
# OR
sudo ss -tlnp | grep 8888
# OR
sudo lsof -i :8888
```

You should see the FastAPI/uvicorn process listening on port 8888.

### 3. Test the backend directly (bypass nginx)

```bash
# Test if FastAPI is responding on port 8888
curl http://127.0.0.1:8888/health

# Test the specific endpoint
curl http://127.0.0.1:8888/api/formula/wish-history?limit=10&offset=0
```

If this works, the backend is fine but nginx can't reach it.
If this fails, the backend isn't running or crashed.

### 4. Check nginx error logs

```bash
# Check nginx error logs for connection issues
sudo tail -f /var/log/nginx/capi_error.log

# Look for errors like:
# - "connect() failed (111: Connection refused)"
# - "upstream prematurely closed connection"
```

### 5. Verify nginx config is correct

```bash
# Test nginx configuration
sudo nginx -t

# Check the proxy_pass setting
sudo grep -A 5 "proxy_pass" /etc/nginx/sites-available/capi.skintruth.in
```

Should show: `proxy_pass http://127.0.0.1:8888;`

### 6. Check service configuration

Find your service file (usually `/etc/systemd/system/chatbot.service`):

```bash
# Check the service file
sudo cat /etc/systemd/system/chatbot.service
```

Make sure it's configured to run on port 8888, for example:
```ini
[Service]
ExecStart=/path/to/uvicorn app.main:app --host 0.0.0.0 --port 8888
```

### 7. Restart everything

```bash
# Restart the FastAPI service
sudo systemctl restart chatbot

# Wait a few seconds, then check status
sleep 3
sudo systemctl status chatbot

# Reload nginx
sudo systemctl reload nginx

# Test again
curl -I https://capi.skintruth.in/health
```

## Common Issues

### Issue 1: Service not running
**Solution:** Start the service
```bash
sudo systemctl start chatbot
sudo systemctl enable chatbot  # Enable on boot
```

### Issue 2: Wrong port
**Solution:** Check if service is running on a different port
```bash
# Find what port the service is actually using
sudo netstat -tlnp | grep python
# OR check the service file
sudo cat /etc/systemd/system/chatbot.service | grep port
```

### Issue 3: Service crashed
**Solution:** Check logs and fix the error
```bash
# Check recent logs
sudo journalctl -u chatbot -n 200 --no-pager

# Look for Python errors, import errors, etc.
```

### Issue 4: Port conflict
**Solution:** Another service might be using port 8888
```bash
# Find what's using port 8888
sudo lsof -i :8888

# Kill the conflicting process if needed (be careful!)
sudo kill -9 <PID>
```

### Issue 5: Firewall blocking
**Solution:** Check firewall rules (though localhost shouldn't be blocked)
```bash
# Check if ufw is blocking (unlikely for localhost)
sudo ufw status
```

## Expected Service Configuration

Your service should be running something like:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8888
```

Or with gunicorn:
```bash
gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8888
```

## Verification

After fixing, verify it works:

```bash
# 1. Service is running
sudo systemctl status chatbot | grep "active (running)"

# 2. Port is listening
sudo netstat -tlnp | grep 8888

# 3. Backend responds directly
curl http://127.0.0.1:8888/health

# 4. Nginx can proxy to it
curl -I https://capi.skintruth.in/health
```

If all 4 steps pass, the 502 error should be resolved!

