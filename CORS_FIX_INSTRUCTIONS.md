# CORS Error Fix Instructions

## Problem
You're getting a CORS error when making requests from `http://localhost:5174` to `https://capi.skintruth.in` because the production server isn't allowing that origin.

## Root Cause
The production server at `https://capi.skintruth.in` needs to have CORS configured to allow requests from `http://localhost:5174`. While your local codebase has CORS configured in `app/main.py`, this configuration only works if it's deployed to the production server.

## Solutions

### Solution 1: Deploy Latest Code to Production (Recommended)
The FastAPI app in `app/main.py` already has CORS configured with `http://localhost:5174` in the allowed origins (line 219). You need to:

1. **Deploy the latest code** to your production server
2. **Restart the FastAPI application** on the production server
3. **Verify** the CORS middleware is active

### Solution 2: Update Nginx Configuration (Fallback)
I've updated `capi.skintruth.in.nginx.conf` to add CORS headers as a fallback. However, note that:

- The `map` directive should be placed in the main `nginx.conf` file (in the `http` context), not in the site-specific config
- Or you can use a simpler approach without the `map` directive

**To apply the nginx fix:**

1. **If using the map directive approach:**
   - Add the `map $http_origin $cors_origin` block to your main `/etc/nginx/nginx.conf` file (inside the `http` block, before any `server` blocks)
   - Then update the site config at `/etc/nginx/sites-available/capi.skintruth.in` with the updated location block

2. **Or use a simpler approach** (see alternative config below)

3. **After updating nginx config:**
   ```bash
   sudo nginx -t  # Test configuration
   sudo systemctl reload nginx  # Reload nginx
   ```

### Solution 3: Use Development Proxy (Quick Fix for Local Development)
If you're developing locally, you can configure your frontend dev server to proxy requests to avoid CORS:

**For Vite (if using Vite):**
Add to `vite.config.js`:
```javascript
export default {
  server: {
    proxy: {
      '/api': {
        target: 'https://capi.skintruth.in',
        changeOrigin: true,
        secure: true
      }
    }
  }
}
```

Then use `/api` instead of `https://capi.skintruth.in/api` in your frontend code.

## Alternative Simple Nginx CORS Config (No Map Directive)

If you prefer not to use the `map` directive, here's a simpler version that works entirely within the server block:

```nginx
location / {
    # Handle preflight OPTIONS requests
    if ($request_method = 'OPTIONS') {
        # Check if origin is allowed
        set $cors_origin "";
        if ($http_origin ~* "^https://tt\.skintruth\.in$") { set $cors_origin $http_origin; }
        if ($http_origin ~* "^https://capi\.skintruth\.in$") { set $cors_origin $http_origin; }
        if ($http_origin ~* "^http://localhost:5174$") { set $cors_origin $http_origin; }
        if ($http_origin ~* "^http://localhost:5173$") { set $cors_origin $http_origin; }
        if ($http_origin ~* "^http://localhost:3000$") { set $cors_origin $http_origin; }
        if ($http_origin ~* "^http://localhost:8000$") { set $cors_origin $http_origin; }
        if ($http_origin ~* "^http://localhost:8501$") { set $cors_origin $http_origin; }
        if ($http_origin ~* "^https://metaverse\.skinbb\.com$") { set $cors_origin $http_origin; }
        if ($http_origin ~* "^https://formulynx\.in$") { set $cors_origin $http_origin; }
        if ($http_origin ~* "^https://www\.formulynx\.in$") { set $cors_origin $http_origin; }
        
        add_header 'Access-Control-Allow-Origin' $cors_origin always;
        add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, PATCH, DELETE, OPTIONS, HEAD' always;
        add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range,Authorization' always;
        add_header 'Access-Control-Allow-Credentials' 'true' always;
        add_header 'Access-Control-Max-Age' 1728000 always;
        add_header 'Content-Length' 0 always;
        return 204;
    }
    
    # ... rest of proxy configuration
}
```

## Verification

After applying any fix, test with:
```bash
curl -H "Origin: http://localhost:5174" \
     -H "Access-Control-Request-Method: GET" \
     -H "Access-Control-Request-Headers: Authorization" \
     -X OPTIONS \
     https://capi.skintruth.in/api/inspiration-boards/boards
```

You should see `Access-Control-Allow-Origin: http://localhost:5174` in the response headers.

## Best Practice

**The recommended approach is Solution 1** - ensure your production FastAPI server has the latest code with CORS middleware configured. The nginx CORS headers should only be used as a fallback or if you can't update the FastAPI application immediately.

