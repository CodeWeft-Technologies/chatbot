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
    git \
    curl \
    wget \
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

# ---------- Playwright ----------
RUN playwright install --with-deps chromium

# ---------- NLTK data ----------
COPY setup_nltk_data.py .
RUN python setup_nltk_data.py

# ---------- App code ----------
COPY . .

# ---------- Expose port ----------
EXPOSE 8000

# ---------- Start server ----------
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
