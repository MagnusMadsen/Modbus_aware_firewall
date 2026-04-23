FROM python:3.11-slim

WORKDIR /app

RUN apt update && apt install -y \
    iproute2 \
    libpcap-dev \
    tcpdump \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

RUN apt-get update && apt-get install -y snmp && rm -rf /var/lib/apt/lists/*

COPY . /app

CMD ["python", "app/main.py"]