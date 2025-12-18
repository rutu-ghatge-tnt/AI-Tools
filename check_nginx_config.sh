#!/bin/bash
# Script to check and fix capi.skintruth.in nginx configuration

echo "=== Checking capi.skintruth.in nginx configuration ==="
echo ""

# Show the current configuration
echo "1. Current configuration file content:"
echo "----------------------------------------"
sudo cat /etc/nginx/sites-available/capi.skintruth.in
echo ""
echo ""

# Check if proxy_pass is configured
echo "2. Checking for proxy_pass configuration:"
echo "----------------------------------------"
sudo grep -n "proxy_pass" /etc/nginx/sites-available/capi.skintruth.in || echo "❌ No proxy_pass found!"
echo ""
echo ""

# Check for location blocks
echo "3. Location blocks in config:"
echo "----------------------------------------"
sudo grep -n "location" /etc/nginx/sites-available/capi.skintruth.in || echo "❌ No location blocks found!"
echo ""
echo ""

# Check what port FastAPI is running on
echo "4. Checking if FastAPI is running:"
echo "----------------------------------------"
ps aux | grep -E "uvicorn|gunicorn|python.*main.py" | grep -v grep || echo "⚠️  FastAPI process not found"
echo ""

# Check if port 8000 is listening
echo "5. Checking if port 8000 is listening:"
echo "----------------------------------------"
netstat -tlnp | grep 8000 || ss -tlnp | grep 8000 || echo "⚠️  Port 8000 not listening"
echo ""

# Test FastAPI locally
echo "6. Testing FastAPI locally:"
echo "----------------------------------------"
curl -s http://localhost:8000/docs | head -20 || echo "❌ FastAPI not responding on localhost:8000"
echo ""

echo "=== Diagnostic complete ==="

