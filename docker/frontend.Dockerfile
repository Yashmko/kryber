# syntax=docker/dockerfile:1
FROM node:20-alpine AS deps
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install

FROM node:20-alpine AS builder
WORKDIR /app
ARG API_URL=http://backend:8000
ENV API_URL=$API_URL
COPY --from=deps /app/node_modules ./node_modules
COPY frontend .
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/public ./public
EXPOSE 3000
CMD ["npm", "run", "start", "--", "-H", "0.0.0.0"]
