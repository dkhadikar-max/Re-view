# Build context = repository root (Railway: Dockerfile path = frontend/Dockerfile)
# Do NOT also set Root Directory to frontend, or paths will break.
FROM node:22-alpine AS deps
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

FROM node:22-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY frontend/ .
ENV NEXT_TELEMETRY_DISABLED=1
# INTERNAL_API_URL is used at runtime by Next rewrites; bake a placeholder for build.
ARG INTERNAL_API_URL=http://127.0.0.1:8000
ENV INTERNAL_API_URL=$INTERNAL_API_URL
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
RUN addgroup -S nodejs && adduser -S nextjs -G nodejs
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
USER nextjs
EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME=0.0.0.0
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD wget -qO- http://127.0.0.1:${PORT:-3000}/login >/dev/null || exit 1
CMD ["sh", "-c", "node server.js"]
