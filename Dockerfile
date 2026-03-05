# Use the official Python image
FROM python:3.11-slim

# Install uv for fast dependency management
ENV HOME="/root"
RUN pip install uv

# Set the working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies globally
RUN uv export > requirements.txt && pip install -r requirements.txt

# Copy source code
COPY . .

# Ensure the cache volume point exists
RUN mkdir -p /root/.cache/huggingface

# Run directly
CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000"]
