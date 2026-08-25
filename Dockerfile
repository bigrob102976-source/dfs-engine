# Big Money DFS -- production image (Milestone 33.3).
#
# ONE image serves BOTH the WEB and WORKER services described in
# DEPLOYMENT.md's service topology -- they are the same codebase started
# two different ways (`npm run start` vs `node scripts/run-job-worker.ts`,
# see that file for why a separate WORKER is optional at all). Building
# two images would mean two copies of the same dependency-install and
# Next.js build steps for no real benefit.
#
# Two runtimes are required in the SAME final image, not just at build
# time: the Next.js server (WEB) spawns Python as a subprocess for every
# slate Process/Refresh (lib/orchestrator/pythonRunner.ts), and the
# standalone WORKER runs those same Python-spawning job handlers directly
# -- Python is a genuine runtime dependency of the running Node process,
# not just a build tool.
#
# NOT BUILT OR PUSHED as part of this milestone -- see this milestone's
# own "DO NOT deploy" instruction. This file has not been validated with
# a real `docker build` (Docker was not available in the environment this
# was written in); every path/command in it was instead verified to work
# via the equivalent plain shell commands this same environment CAN run
# (see DEPLOYMENT.md's "Clean-environment validation" section for exactly
# what was and wasn't confirmed).

# syntax=docker/dockerfile:1

ARG NODE_IMAGE=node:24-slim
ARG PYTHON_IMAGE=python:3.13-slim

# ---------------------------------------------------------------------
# Base: Node (matches .nvmrc) with a pinned Python (matches
# .python-version, and exactly the interpreter data/models/*/metadata.json
# records the trained models were built against -- see requirements.txt's
# own docstring on why that match matters for joblib/scikit-learn
# unpickling). Debian's own apt repos do not reliably offer this exact
# CPython minor version, so the interpreter is copied in from the
# official Python image instead of apt-installed.
# ---------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS python-runtime

FROM ${NODE_IMAGE} AS base
COPY --from=python-runtime /usr/local /usr/local
RUN ln -sf /usr/local/bin/python3 /usr/local/bin/python \
    && python --version \
    && pip --version

# ---------------------------------------------------------------------
# Node dependencies (cached separately from application source so a
# source-only change doesn't invalidate this layer).
# ---------------------------------------------------------------------
FROM base AS node-deps
WORKDIR /app/dashboard
COPY dashboard/package.json dashboard/package-lock.json ./
RUN npm ci

# ---------------------------------------------------------------------
# Next.js production build.
# ---------------------------------------------------------------------
FROM base AS node-build
WORKDIR /app/dashboard
COPY --from=node-deps /app/dashboard/node_modules ./node_modules
COPY dashboard/ .
ENV NODE_ENV=production
RUN npm run build

# ---------------------------------------------------------------------
# Runtime image.
# ---------------------------------------------------------------------
FROM base AS runtime
WORKDIR /app

# Python production dependencies (see requirements.txt's own docstring
# for why versions are pinned exactly, and why requirements-dev.txt --
# pytest -- is deliberately NOT installed here).
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Application source -- Python packages/scripts at the repo root, plus
# the dashboard/ Next.js app. .dockerignore keeps this to real source:
# no node_modules, no .git, no generated artifact directories, no env
# files, no historical warehouse/model data (see .dockerignore's own
# comments -- models are fetched from object storage at runtime,
# Milestone 33.2 Part 7).
COPY . .

# Layer the Next.js build + its node_modules on top of the plain source
# copy above (which does not include node_modules/.next, both
# .dockerignore'd).
COPY --from=node-deps /app/dashboard/node_modules ./dashboard/node_modules
COPY --from=node-build /app/dashboard/.next ./dashboard/.next

WORKDIR /app/dashboard
ENV NODE_ENV=production
EXPOSE 3000

# WEB is the default command. WORKER runs the SAME image with a
# different command -- see DEPLOYMENT.md's "WEB start command" / "WORKER
# start command" for the exact invocations (including why a plain
# `node scripts/run-job-worker.ts` needs no ts-node/tsx at all -- Node's
# own native TypeScript type-stripping, unflagged since Node 23.6, is
# the entire mechanism).
CMD ["npm", "run", "start"]
