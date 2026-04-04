FROM python:3.12-slim

WORKDIR /app

COPY core/ /app/core/
COPY cli/ /app/cli/
COPY mcp/ /app/mcp/

RUN pip install --no-cache-dir /app/core /app/cli /app/mcp

ENTRYPOINT ["mantecato-mcp"]
