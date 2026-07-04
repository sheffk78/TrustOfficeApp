# Build stage
FROM node:18-alpine AS build
WORKDIR /app
COPY package.json yarn.lock ./
RUN yarn install --frozen-lockfile
COPY . .
RUN npx craco build

# Serve stage
FROM node:18-alpine AS serve
RUN npm install -g serve
WORKDIR /app
COPY --from=build /app/build ./build
EXPOSE $PORT
CMD ["sh", "-c", "serve -s build -l ${PORT:-3000}"]