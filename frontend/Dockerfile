FROM node:20-alpine AS build
WORKDIR /app
COPY package.json yarn.lock ./
RUN npm install --force
COPY . .

ARG REACT_APP_BACKEND_URL
ARG REACT_APP_GOOGLE_CLIENT_ID
ENV REACT_APP_BACKEND_URL=$REACT_APP_BACKEND_URL
ENV REACT_APP_GOOGLE_CLIENT_ID=$REACT_APP_GOOGLE_CLIENT_ID
ENV CI=false

RUN yarn build

FROM nginx:alpine
COPY --from=build /app/build /usr/share/nginx/html
RUN chmod -R 755 /usr/share/nginx/html && \
    find /usr/share/nginx/html -type f -exec chmod 644 {} \;

COPY nginx.conf /etc/nginx/conf.d/default.conf

CMD sed -i "s/listen 80/listen ${PORT:-80}/" /etc/nginx/conf.d/default.conf && nginx -g "daemon off;"
