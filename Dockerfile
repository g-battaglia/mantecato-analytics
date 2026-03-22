# ─── Stage 1: Dependencies ───────────────────────────────────────────────────
FROM node:22-alpine AS deps

WORKDIR /app

# Copy package files
COPY package.json package-lock.json ./
COPY prisma/schema.prisma prisma/
COPY prisma.config.ts ./

# Install dependencies (--legacy-peer-deps for react-simple-maps)
RUN npm ci --legacy-peer-deps

# ─── Stage 2: Build ──────────────────────────────────────────────────────────
FROM node:22-alpine AS builder

WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Generate Prisma client
RUN npx prisma generate

# Build Next.js (standalone output)
# Dummy DATABASE_URL so Prisma client initializes during page data collection
# (the real URL is provided at runtime via env vars)
ENV NEXT_TELEMETRY_DISABLED=1
ENV DATABASE_URL="postgresql://dummy:dummy@localhost:5432/dummy?sslmode=disable"
ENV SESSION_SECRET="build-time-placeholder"
RUN npm run build

# ─── Stage 3: Production ─────────────────────────────────────────────────────
FROM node:22-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# Create non-root user
RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

# Copy built assets
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

# Copy Prisma schema + generated client (needed at runtime)
# Prisma 7.5 with engineType="client" generates to src/generated/prisma/
# and uses @prisma/adapter-pg — no node_modules/.prisma directory exists
COPY --from=builder /app/prisma ./prisma
COPY --from=builder /app/src/generated ./src/generated
COPY --from=builder /app/node_modules/@prisma ./node_modules/@prisma
COPY --from=builder /app/node_modules/pg ./node_modules/pg

# Copy CLI and MCP server (for running outside the web server)
COPY --from=builder /app/src/cli ./src/cli
COPY --from=builder /app/src/mcp ./src/mcp
COPY --from=builder /app/src/queries ./src/queries
COPY --from=builder /app/src/lib ./src/lib

USER nextjs

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

CMD ["node", "server.js"]
