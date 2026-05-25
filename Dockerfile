FROM python:3.13-slim-bookworm

WORKDIR /app

# Copy requirements
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
  CMD python -c "import os; os.kill(1, 0)"

CMD ["python", "application.py"]
