#!/bin/sh
set -e

# Railway custom domain is configured with targetPort 80.
# Keep nginx on 80 so the edge can reach the container.
sed -i "s/listen 80/listen 80/" /etc/nginx/conf.d/default.conf
echo "Starting nginx on port 80"
nginx -g "daemon off;"
