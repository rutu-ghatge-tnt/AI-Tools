# CORS Troubleshooting Guide

## Quick Debug Steps

### 1. Check if the code is deployed and server restarted

On your server (`capi.skintruth.in` or `capi.skinbb.com`):

```bash
# Pull latest code
cd /var/www/html/SkinBB_Assistant  # or your project path
git pull origin main

# Restart the service
sudo systemctl restart chatbot

# Check logs to see CORS configuration
sudo journalctl -u chatbot -n 50 --no-pager | grep CORS
```

You should see output like:
```
🌍 CORS: Development mode (capi.skintruth.in)
📋 Allowed CORS origins: ['https://capi.skintruth.in', 'https://tt.skintruth.in', ...]
```

### 2. Test CORS with the debug endpoint

```bash
# Test from your frontend origin
curl -H "Origin: https://tt.skintruth.in" \
     https://capi.skintruth.in/cors-debug

# Or test from localhost
curl -H "Origin: http://localhost:5174" \
     https://capi.skintruth.in/cors-debug
```

This will show you:
- What origin is being sent
- What origins are allowed
- Whether the origin is in the allowed list

### 3. Test actual API endpoint with CORS

```bash
# Test preflight OPTIONS request
curl -X OPTIONS \
     -H "Origin: https://tt.skintruth.in" \
     -H "Access-Control-Request-Method: GET" \
     -H "Access-Control-Request-Headers: Authorization" \
     https://capi.skintruth.in/api/inspiration-boards/boards \
     -v

# Check for Access-Control-Allow-Origin header in response
```

### 4. Verify SERVER_URL in .env

On your server, check the `.env` file:

```bash
# For development server (capi.skintruth.in)
SERVER_URL=https://capi.skintruth.in

# For production server (capi.skinbb.com)
SERVER_URL=https://capi.skinbb.com
```

### 5. Check browser console for exact error

The browser console will show:
- The exact origin being blocked
- The exact API URL being called
- The exact error message

Common issues:
- **Origin mismatch**: The origin in the error doesn't match any in `allowed_origins`
- **Protocol mismatch**: `http://` vs `https://`
- **Port mismatch**: Missing or wrong port number
- **Trailing slash**: Extra `/` at the end

## Common Fixes

### Fix 1: Origin not in allowed list

If your frontend is at `https://tt.skintruth.in` but you're getting CORS errors:

1. Check that `https://tt.skintruth.in` is in the `allowed_origins` list
2. Make sure there's no trailing slash: `https://tt.skintruth.in/` ❌ vs `https://tt.skintruth.in` ✅
3. Check protocol: `http://` vs `https://` must match exactly

### Fix 2: Server not restarted

After updating code, **always restart**:
```bash
sudo systemctl restart chatbot
```

### Fix 3: Environment variable not set

Make sure `SERVER_URL` is set correctly in `.env`:
```bash
# Check current value
grep SERVER_URL .env

# If wrong, update it
nano .env
# Set: SERVER_URL=https://capi.skintruth.in  (for dev)
# Or:  SERVER_URL=https://capi.skinbb.com      (for prod)
```

### Fix 4: Nginx interfering

If FastAPI CORS is configured but still getting errors, nginx might be blocking:

```bash
# Check nginx config
sudo nginx -t

# Check if nginx is adding CORS headers (it shouldn't need to)
curl -I https://capi.skintruth.in/api/inspiration-boards/boards
```

## Expected Behavior

### Development Server (`capi.skintruth.in`)
- Allows: `https://tt.skintruth.in`, `https://capi.skintruth.in`, `http://localhost:*`
- Logs: `🌍 CORS: Development mode (capi.skintruth.in)`

### Production Server (`capi.skinbb.com`)
- Allows: `https://tt.skintruth.in`, `https://capi.skinbb.com`, `https://metaverse.skinbb.com`, etc.
- Does NOT allow: `http://localhost:*`
- Logs: `🌍 CORS: Production mode (capi.skinbb.com)`

## Still Not Working?

1. **Check the exact error message** from browser console
2. **Check server logs** for CORS debug output
3. **Test with curl** to see actual headers
4. **Verify the origin** matches exactly (case-sensitive, no trailing slash)

Share the exact error message and I can help debug further!

