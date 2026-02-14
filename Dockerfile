FROM python:3.11-slim

# Install poppler-utils (required by pdf2image for PDF-to-image conversion)
RUN apt-get update && \
    apt-get install -y --no-install-recommends poppler-utils && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Cloud Run uses PORT env var (default 8080)
ENV PORT=8080

# Use functions-framework to serve the Cloud Function
RUN pip install --no-cache-dir functions-framework

CMD exec functions-framework --target=process_invoice_http --port=${PORT}
