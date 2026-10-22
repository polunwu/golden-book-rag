# Frontend (Next.js 16). Multi-stage: install deps -> build -> slim runtime.

# Node 24 Active LTS. Pinned to the exact patch so picking up a Node security
# release is an explicit, reviewable bump rather than a side effect of build cache.
FROM node:24.22.1-slim AS base
WORKDIR /app

# --- deps: install node_modules (cached on yarn.lock) ---
FROM base AS deps
COPY package.json yarn.lock ./
RUN yarn install --frozen-lockfile

# --- build: compile the Next.js app ---
FROM base AS build
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# Next bakes rewrites() into routes-manifest.json at BUILD time, so the backend
# URL must be set BEFORE `yarn build` (a runtime env var is ignored for rewrites).
# Pass per-environment via --build-arg / compose build.args. Default = local dev.
ARG BACKEND_ORIGIN=http://localhost:8000
ENV BACKEND_ORIGIN=$BACKEND_ORIGIN
RUN yarn build

# --- run: only what's needed to serve ---
FROM base AS run
ENV NODE_ENV=production
COPY --from=build /app/.next ./.next
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/public ./public
COPY --from=build /app/package.json ./package.json
COPY --from=build /app/next.config.ts ./next.config.ts

ENV PORT=3000
EXPOSE 3000
# `next start` serves the production build AND runs the /api/* rewrite server-side.
CMD ["yarn", "start"]
