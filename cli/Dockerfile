FROM python:3.12-slim

WORKDIR /app

COPY core/ /app/core/
COPY cli/ /app/cli/

RUN pip install --no-cache-dir /app/core /app/cli

ENTRYPOINT ["mantecato"]
