FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    COURSEBEE_DATA_ROOT=/app/outputs \
    COURSEBEE_OCR_LANG=eng+kor

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-kor \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-v2.txt ./
RUN pip install --no-cache-dir -r requirements-v2.txt

ARG COURSEBEE_INSTALL_SEMANTIC=false
ARG COURSEBEE_TORCH_VERSION=2.12.1
RUN if [ "$COURSEBEE_INSTALL_SEMANTIC" = "true" ]; then \
        pip install --no-cache-dir \
            --index-url https://download.pytorch.org/whl/cpu \
            "torch==$COURSEBEE_TORCH_VERSION" \
        && \
        pip install --no-cache-dir "sentence-transformers>=5.6,<6"; \
    fi

COPY . .
RUN useradd --create-home --uid 10001 coursebee \
    && mkdir -p /app/outputs \
    && chown -R coursebee:coursebee /app

USER coursebee
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=3)"

CMD ["uvicorn", "v2.main:app", "--host", "0.0.0.0", "--port", "8000"]
