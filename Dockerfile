FROM python:3.11-slim

# tesseract-ocr + poppler-utils enable the OCR fallback path for scanned
# pages (pdf_ingest.py). Comment out if you don't need OCR and want a
# smaller image -- also uncomment pytesseract/pdf2image in requirements.txt
# if you keep this.
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
