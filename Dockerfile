# ── Job Application & AI Tailoring Hub ──────────────────────────
# Standalone container packaging:
#   • Python 3.11 web runtime (dashboard & API)
#   • Typst compiler (for CV / motivation letter PDF generation)
#   • Roboto fonts (Typst fallback font family)
# ─────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS base

ENV DEBIAN_FRONTEND=noninteractive

# ── System dependencies ──────────────────────────────────────────
# Minimal runtime dependencies: curl, ca-certificates, and xz-utils
# for downloading Typst binary, and fonts-roboto for PDF compilation.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    xz-utils \
    fonts-roboto \
    && rm -rf /var/lib/apt/lists/*

# ── Typst binary ─────────────────────────────────────────────────
ARG TYPST_VERSION=0.15.0
RUN curl --retry 3 --retry-delay 2 -fsSL "https://github.com/typst/typst/releases/download/v${TYPST_VERSION}/typst-x86_64-unknown-linux-musl.tar.xz" \
        -o /tmp/typst.tar.xz && \
    tar -xf /tmp/typst.tar.xz -C /tmp && \
    mv /tmp/typst-x86_64-unknown-linux-musl/typst /usr/local/bin/typst && \
    chmod +x /usr/local/bin/typst && \
    rm -rf /tmp/typst*

# ── Working directory ────────────────────────────────────────────
WORKDIR /app

# ── Application source + Python dependencies ─────────────────────
COPY pyproject.toml ./
COPY jobhunt/       ./jobhunt/
COPY dashboard/     ./dashboard/
COPY config/        ./config/
COPY Base/          ./Base/

RUN pip install --no-cache-dir .

# ── Runtime configuration ────────────────────────────────────────
VOLUME ["/app/data", "/app/Applications", "/app/config"]

EXPOSE 8765

ENTRYPOINT ["python", "-m", "jobhunt", "dashboard", "--host", "0.0.0.0", "--port", "8765"]
