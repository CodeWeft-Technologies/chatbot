# ---------- Base image ----------
FROM python:3.11-slim

# ---------- System dependencies (CRITICAL for hi_res) ----------
RUN apt-get update && apt-get install -y \
    poppler-utils \
    tesseract-ocr \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgbm1 \
    git \
    curl \
    wget \
    fonts-liberation \
    fonts-noto-core \
    fonts-noto-mono \
    xdg-utils \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    && rm -rf /var/lib/apt/lists/*

# ---------- Environment ----------
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV NLTK_DATA=/usr/local/share/nltk_data

# ---------- Working directory ----------
WORKDIR /app

# ---------- Install Python deps ----------
COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install -r requirements.txt 

# ---------- NLTK data ----------
COPY setup_nltk_data.py .
RUN python setup_nltk_data.py

# ---------- App code ----------
COPY . .

# ---------- Expose port ----------
EXPOSE 8000

# ---------- Entrypoint ----------
RUN echo '#!/bin/sh' > /app/entrypoint.sh && \
    echo 'exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1' >> /app/entrypoint.sh && \
    chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
