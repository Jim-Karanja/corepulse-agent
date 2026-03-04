FROM python:3.11-slim

# Install system diagnostic tools
RUN apt-get update && apt-get install -y \
    iputils-ping \
    smartmontools \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "app/main.py"]