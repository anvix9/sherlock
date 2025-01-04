
FROM pytorch/pytorch:2.0.1-cuda11.7-cudnn8-runtime

# Install Python tools and dependencies
RUN apt-get update && apt-get install -y \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Install docling without torch (to manage torch version manually)
RUN pip install --no-cache-dir pytest pytest-cov docling

# Install any other required dependencies here
