# Big Money DFS -- production image (Milestone 33.3).
#
# ONE image serves BOTH the WEB and WORKER services described in
# DEPLOYMENT.md's service topology -- they are the same codebase started
# two different ways (`npm run start` vs `npm run worker`, see that file
# for why a separate WORKER is optional at all). Building
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
# Docker remains unavailable in the environment this file is edited in,
# so changes here still cannot be `docker build`-validated locally --
# every path/command in it is instead verified to work via the
# equivalent plain shell commands this environment CAN run (see
# DEPLOYMENT.md's "Clean-environment validation" section for exactly
# what was and wasn't confirmed that way). As of Milestone 33.5 this
# image IS built for real by Railway on every push -- the base-image
# pinning fix a few lines down exists because that real build failed
# and is now the authoritative validation this file gets.

# syntax=docker/dockerfile:1

# Both pinned to the same explicit Debian codename (bookworm) -- see the
# "python-runtime"/"base" stages below for why that match is required,
# not optional. Do not switch either back to an untagged "slim" (which
# floats to Docker Hub's current default Debian release independently
# for each image) without re-verifying both still resolve to the same
# release.
ARG NODE_IMAGE=node:24-bookworm-slim
ARG PYTHON_IMAGE=python:3.13-slim-bookworm

# ---------------------------------------------------------------------
# Base: Node (matches .nvmrc) with a pinned Python (matches
# .python-version, and exactly the interpreter data/models/*/metadata.json
# records the trained models were built against -- see requirements.txt's
# own docstring on why that match matters for joblib/scikit-learn
# unpickling). Debian's own apt repos do not reliably offer this exact
# CPython minor version, so the interpreter is copied in from the
# official Python image instead of apt-installed.
#
# Milestone 33.5 real Railway build failure + fix: the untagged "slim"
# variants of the node and python base images each float independently
# to whatever Debian release Docker Hub currently publishes as their
# default -- they are NOT guaranteed to be the same release. When they
# drift apart (python:3.13-slim resolving to a newer Debian than
# node:24-slim), the Python interpreter/shared libraries copied below
# are linked against a newer glibc than the Node base image provides,
# and every `python`/`pip` invocation fails at runtime
# (`/usr/local/bin/python3: version 'GLIBC_2.xx' not found`). This is
# NOT a "copy some /usr/local into a base image" problem in general --
# it only breaks when the two base images are different Debian
# releases. The fix is pinning BOTH images to the exact same Debian
# codename explicitly, so the copied Python is always built against the
# identical glibc already present in the target base.
# ---------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS python-runtime

FROM ${NODE_IMAGE} AS base
COPY --from=python-runtime /usr/local /usr/local

# Milestone 33.5, second real Railway build failure: the COPY above only
# brings in /usr/local, which is where Python's own files (interpreter,
# stdlib, compiled extension modules like _ssl.cpython-313-*.so) live --
# but the OpenSSL shared libraries those extensions dynamically link
# against (libssl.so.3 / libcrypto.so.3) live under /usr/lib/<triplet>/
# in the python-runtime image, an ordinary Debian package path outside
# /usr/local, so they were never copied. node:24-bookworm-slim never
# installs libssl3 itself (Node statically bundles its own OpenSSL), so
# the copied _ssl module failed to load its dependency and `pip install`
# failed outright ("ssl module is unavailable", every HTTPS fetch to
# PyPI refused). Fix: install the missing OS packages via apt directly
# in this Debian bookworm base -- ca-certificates provides the trust
# store pip's TLS verification also needs -- rather than trying to copy
# more of python-runtime's filesystem across.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates libssl3 \
    && rm -rf /var/lib/apt/lists/*

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
# different command (`npm run worker`) -- see DEPLOYMENT.md's "Node"
# section for why that runs via `tsx` rather than plain `node`
# (Milestone 33.4: this codebase's normal extensionless internal-import
# style, resolved fine by Next.js's bundler, is NOT resolved by Node's
# own native ESM loader -- confirmed live, a real startup crash before
# this was fixed).
CMD ["npm", "run", "start"]
