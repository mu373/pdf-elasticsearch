FROM python:3.11-slim-buster

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY pdf_indexer.py .

CMD ["python", "pdf_indexer.py"]

