FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

RUN groupadd -r -g 10001 appuser && useradd -r -u 10001 -g appuser appuser

COPY . /app

RUN chown -R appuser:appuser /app

USER appuser

CMD ["python", "app/main.py"]