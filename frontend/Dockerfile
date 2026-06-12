FROM node:20-alpine AS build
WORKDIR /app
# Build cache bust — logo update Jun 2026
ARG CACHE_BUST=1
COPY package.json yarn.lock ./
RUN npm install --force
COPY . .

ARG REACT_APP_BACKEND_URL
ARG REACT_APP_GOOGLE_CLIENT_ID
ENV REACT_APP_BACKEND_URL=$REACT_APP_BACKEND_URL
ENV REACT_APP_GOOGLE_CLIENT_ID=$REACT_APP_GOOGLE_CLIENT_ID
ENV CI=false

RUN npm run build

FROM nginx:alpine
COPY --from=build /app/build /usr/share/nginx/html
RUN chmod -R 755 /usr/share/nginx/html && \
    find /usr/share/nginx/html -type f -exec chmod 644 {} \;

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

# Railway assigns $PORT at runtime; start.sh dynamically configures nginx to listen on it
EXPOSE 80

CMD ["/app/start.sh"]
