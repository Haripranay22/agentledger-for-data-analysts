FROM python:3.11-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first (better layer caching)
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[dashboard]" \
    && pip install --no-cache-dir boto3

# Copy source
COPY src/ ./src/
COPY dashboard/ ./dashboard/
COPY .streamlit/ ./.streamlit/
COPY models/ ./models/

# Create output dirs
RUN mkdir -p reports/reviews output/memos evals

EXPOSE 8501

HEALTHCHECK --interval=10s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "dashboard/app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0"]
