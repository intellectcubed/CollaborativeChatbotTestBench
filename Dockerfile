# Stage 1: build the React page (ui/) into ui/dist.
FROM node:22-slim AS ui
WORKDIR /ui
COPY ui/package.json ui/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY ui/ ./
RUN npm run build

# Stage 2: the driver.
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

# Dependencies come from pyproject.toml. Rebuild the image only when they change.
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

# The built page. It sits outside src/, so the development mount of ./src does not hide it.
COPY --from=ui /ui/dist /app/ui/dist

# Code is not baked in for development: compose mounts ./src over this copy and reloads on change.
