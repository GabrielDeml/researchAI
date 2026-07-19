ARG BASE_IMAGE
FROM ${BASE_IMAGE}

ENV PYTHONHASHSEED=1729 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /experiment
COPY monitor.py /experiment/monitor.py
ENTRYPOINT ["python3", "/experiment/monitor.py"]
