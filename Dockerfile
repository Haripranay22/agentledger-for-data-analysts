FROM python:3.11-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy package metadata + source before install (hatchling needs src/ to resolve the package)
COPY pyproject.toml ./
COPY src/ ./src/

# Install all runtime extras in one layer (non-editable for production)
RUN pip install --no-cache-dir ".[dashboard,cloud,plaid,observability]"

# Copy remaining app code (changes here don't bust the pip cache layer above)
COPY dashboard/ ./dashboard/
COPY .streamlit/ ./.streamlit/
COPY models/ ./models/
COPY scripts/ ./scripts/

# Create output dirs
RUN mkdir -p reports/reviews output/memos evals

EXPOSE 8501

HEALTHCHECK --interval=10s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "dashboard/app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0"]
