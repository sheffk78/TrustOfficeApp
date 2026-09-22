# TrustOffice Proton Bridge — bundle stage fixes two SDK-side module problems:
# 1. @protontech/drive-sdk dist ships extensionless ESM imports ('./internal/uids')
# 2. @protontech/crypto imports 'openpgp/lightweight', only exported for browser
# esbuild resolves everything at build time; alias routes lightweight → openpgp
# (Node export). Runtime image carries only the bundle, no node_modules.
FROM node:20-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --include=dev
COPY server.js ./
COPY lib ./lib
RUN ./node_modules/.bin/esbuild server.js --bundle --platform=node \
    --format=esm --target=node20 \
    --alias:openpgp/lightweight=openpgp \
    --banner:js="import { createRequire as __kitCr } from 'module'; const require = __kitCr(import.meta.url);" \
    --outfile=bridge.mjs

FROM node:20-slim
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app/bridge.mjs ./
EXPOSE 8081
CMD ["node", "bridge.mjs"]