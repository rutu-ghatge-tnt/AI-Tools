# Nginx Timeout Fix for 504 Errors

## Problem
The `compare-products` and `make-wish` endpoints were returning 504 Gateway Timeout errors because nginx was timing out before the FastAPI backend could complete processing.

## Root Cause
These endpoints perform long-running operations:
- **compare-products**: Web scraping, multiple product processing, and AI API calls (Claude)
- **make-wish**: 5-stage AI pipeline with multiple AI API calls

These operations can take 10-15 minutes, but nginx was configured with only 300s (5 minutes) timeouts.

## Solution
Increased nginx timeout settings from 300s to 900s (15 minutes):

### Updated Timeout Settings:
- `proxy_connect_timeout`: 900s (was 300s)
- `proxy_send_timeout`: 900s (was 300s)
- `proxy_read_timeout`: 900s (was 300s)
- `send_timeout`: 900s (new)
- `client_body_timeout`: 900s (new)

### Additional Improvements:
- Disabled proxy buffering for better streaming support
- Disabled proxy request buffering

## How to Apply

### Option 1: Use the automated script
```bash
chmod +x apply_nginx_timeout_fix.sh
./apply_nginx_timeout_fix.sh
```

### Option 2: Manual application
1. Backup current config:
   ```bash
   sudo cp /etc/nginx/sites-available/capi.skintruth.in /etc/nginx/sites-available/capi.skintruth.in.backup
   ```

2. Copy new config:
   ```bash
   sudo cp capi.skintruth.in.nginx.conf /etc/nginx/sites-available/capi.skintruth.in
   ```

3. Test configuration:
   ```bash
   sudo nginx -t
   ```

4. Reload nginx:
   ```bash
   sudo systemctl reload nginx
   ```

## Verification
After applying, verify the timeouts are set correctly:
```bash
sudo grep -E "proxy_(connect|send|read)_timeout|send_timeout|client_body_timeout" /etc/nginx/sites-available/capi.skintruth.in
```

You should see all timeouts set to 900s.

## Testing
Test the endpoints:
1. **compare-products**: POST to `/api/compare-products` with multiple product URLs
2. **make-wish**: POST to `/api/make-wish/generate` with wish data

Both should now complete without 504 errors, even for long-running operations.

## Notes
- The 900s timeout should be sufficient for most operations
- If operations consistently take longer than 15 minutes, consider:
  - Optimizing the endpoints (parallel processing, caching)
  - Implementing background job processing
  - Further increasing timeouts (though this is not recommended)

