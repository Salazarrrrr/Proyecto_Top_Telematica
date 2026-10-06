FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home --uid 10001 dfsha \
    && mkdir -p /app/metadata /var/lib/dfsha \
    && chown -R dfsha:dfsha /app /var/lib/dfsha

COPY --chown=dfsha:dfsha Client ./Client
COPY --chown=dfsha:dfsha Gateway ./Gateway
COPY --chown=dfsha:dfsha Node ./Node
COPY --chown=dfsha:dfsha Proto ./Proto

USER dfsha
EXPOSE 8000 50051
CMD ["python", "-m", "Gateway.app"]
