FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

# Dependencies come from pyproject.toml. Rebuild the image only when they change.
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

# Code is not baked in for development: compose mounts ./src over this copy and reloads on change.
