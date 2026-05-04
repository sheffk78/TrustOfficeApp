#!/bin/sh
# Force nginx to listen on port 80 (matching Railway's EXPOSE 80)
# Railway V2 gateway proxies traffic from the external domain to port 80
sed -i "s/listen 80/listen 80/" /etc/nginx/conf.d/default.conf
echo "Starting nginx on port 80 (Railway expects EXPOSE 80)"
nginx -g "daemon off;"
