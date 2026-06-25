#!/bin/sh
# Railway V2 gateway proxies traffic from the external domain to the container's $PORT
# Dynamically update nginx to listen on Railway's assigned port
if [ -n "$PORT" ]; then
    echo "Railway PORT detected: $PORT"
    # Replace ONLY the explicit listen port with the correct one — anchored to avoid compounding
    sed -i "s/^\s*listen [0-9]\+;/    listen $PORT;/" /etc/nginx/conf.d/default.conf
else
    echo "No PORT env var set, defaulting to port 80"
fi
echo "Starting nginx..."
exec nginx -g "daemon off;"