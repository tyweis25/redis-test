FROM ubuntu:24.04

# System dependencies for running the Redis demo scripts/apps:
#   - python3 + venv + pip: run the Flask apps and demo scripts
#   - redis-server / redis-tools: local Redis the scripts connect to on localhost:6379
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 \
        python3-venv \
        python3-pip \
        redis-server \
        redis-tools \
        iproute2 \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

USER ubuntu
