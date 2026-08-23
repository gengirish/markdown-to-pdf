FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

EXPOSE 8000

# Use uvicorn to run the FastAPI app.
#
# --proxy-headers makes uvicorn honour X-Forwarded-Proto/-For instead of the
# socket peer, which behind the Vercel -> Fly rewrite is always the Fly proxy.
# --forwarded-allow-ips="*" is required for that to take effect: only the Fly
# proxy can reach this port, so the peer is trusted by construction. The
# per-client address used for rate limiting is resolved in api/index.py
# (_client_ip), which counts TRUSTED_PROXY_HOPS in from the right of the chain.
CMD ["uvicorn", "api.index:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
