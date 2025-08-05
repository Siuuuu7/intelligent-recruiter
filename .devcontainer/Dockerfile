# Use Python 3.13 as the base image
FROM python:3.13-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    sudo \
    wget \
    unzip \
    ca-certificates \
    gnupg \
    lsb-release \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js and pnpm
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g pnpm@10.7.1

# Install uv (Python package manager)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Create a non-root user
RUN useradd -m -s /bin/bash vscode \
    && echo "vscode ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

# Switch to the vscode user
USER vscode
WORKDIR /home/vscode

# Install uv for the vscode user
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/home/vscode/.local/bin:$PATH"

# Set the workspace directory
WORKDIR /workspaces/a2a-1

# Copy requirements and install Python dependencies
# We'll do this in post-create for better layer caching
# COPY --chown=vscode:vscode demo/ui/pyproject.toml demo/ui/pyproject.toml
# COPY --chown=vscode:vscode samples/python/pyproject.toml samples/python/pyproject.toml

# Set default shell to bash
SHELL ["/bin/bash", "-c"]

# Keep container running
CMD ["sleep", "infinity"]