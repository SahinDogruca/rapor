FROM python:3.9-bookworm

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        pkg-config \
        libcairo2 \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        libgdk-pixbuf2.0-0 \
        libffi-dev \
        shared-mime-info \
        fonts-dejavu-core \
        fonts-liberation \
        xfonts-base \
        xfonts-scalable \
        && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# logo.png dosyasını /app dizinine kopyala
COPY logo.png .
COPY fonts /app/fonts
COPY report_with_api.py .
COPY .env .

CMD ["uvicorn", "report_with_api:app", "--host", "0.0.0.0", "--port", "8000"]