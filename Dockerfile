FROM python:3.11-slim

# -----------------------------
# Set working directory
# -----------------------------
WORKDIR /app

# -----------------------------
# Set environment
# -----------------------------
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=UTC \
    DEBIAN_FRONTEND=noninteractive

# -----------------------------
# Create sessions folder
# -----------------------------
RUN mkdir -p sessions

# -----------------------------
# Install system dependencies
# -----------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    tzdata \
    ca-certificates \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# -----------------------------
# Copy requirements and install
# -----------------------------
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# -----------------------------
# Copy source code
# -----------------------------
COPY . .

# -----------------------------
# Expose folder for sessions (optional, for host mount)
# -----------------------------
VOLUME ["/app/sessions"]

# -----------------------------
# Run bot
# -----------------------------
CMD ["python", "main.py"]
