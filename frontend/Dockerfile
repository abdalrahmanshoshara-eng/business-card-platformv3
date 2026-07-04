# Stage 1 — install dependencies only (layer cache)
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci

# Stage 2 — build the Next.js application
FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# NEXT_PUBLIC_* vars are baked into the client bundle at build time.
# Pass the correct backend URL as a build arg from docker-compose or CI.
ARG NEXT_PUBLIC_BACKEND_URL=http://127.0.0.1:8000
ARG NEXT_PUBLIC_API_BASE_URL=/api
ENV NEXT_PUBLIC_BACKEND_URL=$NEXT_PUBLIC_BACKEND_URL
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL

RUN npm run build

# Stage 3 — minimal production image
FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production

COPY --from=builder /app/public ./public
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/next.config.mjs ./
COPY --from=deps  /app/node_modules ./node_modules
COPY package*.json ./

EXPOSE 3000

# PORT is injected by Render or docker-compose; default 3000
CMD sh -c "node_modules/.bin/next start -H 0.0.0.0 -p ${PORT:-3000}"
