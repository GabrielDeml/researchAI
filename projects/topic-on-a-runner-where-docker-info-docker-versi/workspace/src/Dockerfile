FROM python:3.12-slim

WORKDIR /app
COPY common.py monitor.py supervisor.py workload.py /app/
ENTRYPOINT ["python", "/app/supervisor.py"]
