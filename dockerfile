# Dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY . /app

RUN pip install fastapi uvicorn pydicom psycopg2-binary cryptography

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
