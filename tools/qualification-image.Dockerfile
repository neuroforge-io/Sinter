FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive
# Tooling only: the application comes from the same-run frozen artifact.
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 ca-certificates zlib1g libx11-6 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /work
