#!/bin/bash
# Script to apply nginx timeout fixes for compare-products and make-wish endpoints
# This fixes 504 Gateway Timeout errors

echo "=== Applying Nginx Timeout Fixes ==="
echo ""

# Backup current config
echo "1. Backing up current nginx configuration..."
sudo cp /etc/nginx/sites-available/capi.skintruth.in /etc/nginx/sites-available/capi.skintruth.in.backup.$(date +%Y%m%d_%H%M%S)
echo "   ✅ Backup created"

# Copy new config
echo ""
echo "2. Copying new nginx configuration..."
sudo cp capi.skintruth.in.nginx.conf /etc/nginx/sites-available/capi.skintruth.in
echo "   ✅ Configuration copied"

# Test nginx configuration
echo ""
echo "3. Testing nginx configuration..."
sudo nginx -t
if [ $? -eq 0 ]; then
    echo "   ✅ Nginx configuration is valid"
else
    echo "   ❌ Nginx configuration has errors!"
    echo "   Restoring backup..."
    sudo cp /etc/nginx/sites-available/capi.skintruth.in.backup.* /etc/nginx/sites-available/capi.skintruth.in
    exit 1
fi

# Reload nginx
echo ""
echo "4. Reloading nginx..."
sudo systemctl reload nginx
if [ $? -eq 0 ]; then
    echo "   ✅ Nginx reloaded successfully"
else
    echo "   ❌ Failed to reload nginx!"
    exit 1
fi

# Show the timeout settings
echo ""
echo "5. Current timeout settings:"
echo "----------------------------------------"
sudo grep -E "proxy_(connect|send|read)_timeout|send_timeout|client_body_timeout" /etc/nginx/sites-available/capi.skintruth.in | grep -v "^#" | sed 's/^/   /'

echo ""
echo "=== Fix Applied Successfully ==="
echo ""
echo "Timeout settings have been increased to 900s (15 minutes) for:"
echo "  - proxy_connect_timeout"
echo "  - proxy_send_timeout"
echo "  - proxy_read_timeout"
echo "  - send_timeout"
echo "  - client_body_timeout"
echo ""
echo "This should fix 504 errors for compare-products and make-wish endpoints."
echo ""

