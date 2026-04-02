# Mantecato Architecture

- `frontend/` is the web app: Vite + React SPA.
- `backend/` is the API: FastAPI on port `8100`.
- `src/` is no longer the web app. It is kept only for the CLI, MCP server, Prisma client, and shared TypeScript query code.
- Do not add new Next.js files or reintroduce `next/*` conventions.
