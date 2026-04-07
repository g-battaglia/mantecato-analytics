#!/bin/bash
# Demo environment — ACME Inc. sample data
# Uses Apple Containers on separate ports (no conflict with dev)
#
# Ports: 4181 (frontend), 8101 (backend), 5433 (postgres)
# Login: demo / demo

set -e
cd "$(dirname "$0")/.."

echo "==> Stopping any existing demo containers..."
container stop demo-db demo-backend demo-frontend 2>/dev/null || true
container rm demo-db demo-backend demo-frontend 2>/dev/null || true

echo "==> Starting PostgreSQL (port 5433)..."
container run \
  --name demo-db \
  -e POSTGRES_DB=mantecato_demo \
  -e POSTGRES_USER=mantecato \
  -e POSTGRES_PASSWORD=mantecato \
  -p 5433:5432 \
  -v "$(pwd)/demo/seed.sql:/docker-entrypoint-initdb.d/01-seed.sql" \
  --detach \
  postgres:16-alpine

echo "==> Waiting for PostgreSQL..."
for i in $(seq 1 20); do
  container exec demo-db pg_isready -U mantecato -d mantecato_demo 2>/dev/null && break
  sleep 2
done

echo "==> Verifying seed data..."
container exec demo-db psql -U mantecato -d mantecato_demo -c \
  "SELECT name, (SELECT count(*) FROM website_event) as events FROM website LIMIT 1;"

echo "==> Building backend..."
container build -t mantecato-demo-backend -f demo/Dockerfile.backend \
  --build-context core=core \
  --build-context backend=backend \
  . 2>&1 | tail -3

echo "==> Starting backend (port 8101)..."
container run \
  --name demo-backend \
  -e DATABASE_URL=postgresql://mantecato:mantecato@host.containers.internal:5433/mantecato_demo \
  -e SESSION_SECRET=demo-secret-not-for-production \
  -p 8101:8100 \
  --detach \
  mantecato-demo-backend

echo "==> Building frontend..."
container build -t mantecato-demo-frontend -f demo/Dockerfile.frontend \
  --build-context frontend=frontend \
  . 2>&1 | tail -3

echo "==> Starting frontend (port 4181)..."
container run \
  --name demo-frontend \
  -p 4181:80 \
  --detach \
  mantecato-demo-frontend

echo ""
echo "✓ Demo running!"
echo "  Dashboard: http://localhost:4181"
echo "  API:       http://localhost:8101"
echo "  Login:     demo / demo"
echo ""
echo "Stop with: demo/stop.sh"
