FROM python:3.12-slim

WORKDIR /app

COPY core/ /app/core/
COPY mcp/ /app/mcp/

RUN pip install --no-cache-dir /app/core /app/mcp

CMD ["mantecato-mcp", "--transport", "http"]
