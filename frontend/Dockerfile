FROM node:18-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm install --legacy-peer-deps

COPY public/ public/
COPY src/ src/
COPY craco.config.js ./
COPY tailwind.config.js ./
COPY postcss.config.js ./
COPY tsconfig.json ./

RUN npm run build

FROM node:18-alpine AS serve

RUN npm install -g serve@14.2.6

COPY --from=build /app/build /app/build

EXPOSE 3000

CMD ["sh", "-c", "serve -s /app/build -l ${PORT:-3000}"]