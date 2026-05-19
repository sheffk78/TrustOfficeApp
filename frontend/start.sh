#!/bin/sh
# Railway V2 gateway proxies traffic from the external domain to the container's $PORT
# We dynamically update nginx to listen on Railway's assigned port
if [ -n "$PORT" ]; then
    echo "Railway PORT detected: $PORT"
    sed -i "s/listen 80/listen $PORT/" /etc/nginx/conf.d/default.conf
else
    echo "No PORT env var set, defaulting to port 80"
fi
echo "Starting nginx..."
nginx -g "daemon off;"