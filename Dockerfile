FROM python:3.11-slim

WORKDIR /app

# Zainstaluj zależności systemowe potrzebne przez LightGBM / pandas
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Kopiuj tylko pyproject.toml najpierw (cache layer)
COPY pyproject.toml .

# Instalacja zależności Python
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -e . 2>/dev/null || \
    pip install --no-cache-dir \
        "fastapi>=0.111" \
        "uvicorn[standard]>=0.30" \
        "lightgbm>=4.3" \
        "pandas>=2.2" \
        "numpy>=1.26" \
        "scikit-learn>=1.5" \
        "scipy>=1.13" \
        "joblib>=1.4" \
        "pydantic>=2.0" \
        "python-multipart>=0.0.9"

# Kopiuj cały projekt
COPY . .

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
