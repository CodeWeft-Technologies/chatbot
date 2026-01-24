# ===============================
# Base image
# ===============================
FROM python:3.11-slim

# ===============================
# System dependencies (CRITICAL for unstructured hi_res + Playwright)
# ===============================
RUN apt-get update && apt-get install -y \
    poppler-utils \
    tesseract-ocr \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgbm1 \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    fonts-liberation \
    fonts-noto-core \
    fonts-noto-mono \
    fonts-noto-mono \
    git \
    curl \
    wget \
    xdg-utils \
    ca-certificates \
    libharfbuzz0b \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    && rm -rf /var/lib/apt/lists/*

# ===============================
# Environment
# ===============================
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV NLTK_DATA=/usr/local/share/nltk_data

# ===============================
# Workdir
# ===============================
WORKDIR /app

# ===============================
# Python dependencies
# ===============================
COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ===============================
# Install Playwright browsers
# ===============================
RUN python -m playwright install chromium \
    && python -m playwright install-deps chromium

# ===============================
# Download NLTK data at build time
# ===============================
COPY setup_nltk_data.py .
RUN python setup_nltk_data.py

# ===============================
# App source
# ===============================
COPY . .

# ===============================
# Expose port (Railway ignores but good practice)
# ===============================
EXPOSE 8000

# ===============================
# Start server
# ===============================
CMD ["python", "start.py"]
