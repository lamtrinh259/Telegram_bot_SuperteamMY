FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot ./bot
COPY main.py ./main.py

RUN mkdir -p /app/data

# Switch to non-root user for better security to run the app
RUN useradd -m -u 1000 appuser
USER appuser
CMD ["python", "main.py"]
