# syntax=docker/dockerfile:1.7

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml README.md /app/
COPY src /app/src

ARG TRAMA_PIP_INSECURE=0
RUN --mount=type=secret,id=trama-ca,required=false \
    if [ -s /run/secrets/trama-ca ]; then \
      cp /run/secrets/trama-ca /usr/local/share/ca-certificates/trama-corporate.crt && \
      update-ca-certificates; \
    fi && \
    if [ "$TRAMA_PIP_INSECURE" = "1" ]; then \
      python -m pip install --no-cache-dir --trusted-host pypi.org --trusted-host files.pythonhosted.org .; \
    else \
      python -m pip install --no-cache-dir .; \
    fi

EXPOSE 8090
CMD ["trama", "api", "--host", "0.0.0.0", "--port", "8090"]
