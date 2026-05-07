# Use official Playwright Python image as base
# This image comes with all browsers and OS dependencies pre-installed
FROM mcr.microsoft.com/playwright/python:v1.49.0-noble

# Set working directory
WORKDIR /app

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# We only need to install chromium specifically to keep the image small
# No need for --with-deps as the base image already has them
RUN playwright install chromium

# Copy application source
COPY app/ ./app/

# Set Python to run in unbuffered mode (ensures logs appear in real-time)
ENV PYTHONUNBUFFERED=1

# Expose port
EXPOSE 8000

# Health check for Coolify
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# Run with uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
