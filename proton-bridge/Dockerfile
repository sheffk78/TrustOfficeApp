FROM node:20-slim

WORKDIR /app

# Production deps only; SDK is a regular dependency (ESM, node >=18).
COPY package.json package-lock.json ./
RUN npm ci --omit=dev

COPY server.js ./
COPY lib ./lib

ENV NODE_ENV=production
EXPOSE 8081

CMD ["node", "server.js"]