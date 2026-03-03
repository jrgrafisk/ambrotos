FROM python:3.11-slim

WORKDIR /app

# Installer systemafhængigheder
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
  && rm -rf /var/lib/apt/lists/*

# Installer Python-afhængigheder
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn psycopg2-binary

# Kopiér applikationskode
COPY . .

# Opret mappe til backup-fil
RUN mkdir -p data

EXPOSE 8000

CMD ["gunicorn", "--workers", "2", "--bind", "0.0.0.0:8000", "app:app"]
