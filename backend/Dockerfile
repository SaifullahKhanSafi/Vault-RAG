FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 STORAGE_DIR=/data
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends poppler-utils tesseract-ocr tesseract-ocr-eng && rm -rf /var/lib/apt/lists/*
COPY requirements.txt requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock
RUN useradd --create-home --uid 10001 rag && mkdir -p /data && chown rag:rag /data /app
COPY --chown=rag:rag . .
ARG APP_VERSION=dev
ARG VCS_REF=unknown
ARG SOURCE_URL=https://github.com
LABEL org.opencontainers.image.title="Enterprise RAG API and workers" \
      org.opencontainers.image.version=$APP_VERSION \
      org.opencontainers.image.revision=$VCS_REF \
      org.opencontainers.image.source=$SOURCE_URL
RUN test "$APP_VERSION" = dev || test "$(cat VERSION)" = "$APP_VERSION"
USER rag
EXPOSE 8000
CMD ["uvicorn","main:app","--host","0.0.0.0","--port","8000"]
