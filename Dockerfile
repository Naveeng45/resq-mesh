# MealMesh live demo dashboard (FastAPI + static UI).
# Build from repo root:
#   docker build -t mealmesh .
#   docker run --rm -p 8000:8000 mealmesh
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

# OR-Tools / numpy wheels need a current pip + basic build toolchain on slim.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY examples ./examples

EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.api.server:app --host 0.0.0.0 --port ${PORT}"]
