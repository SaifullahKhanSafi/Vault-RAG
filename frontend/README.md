# Enterprise RAG frontend

Next.js 16 / React 19 / TypeScript workspace client. The application overview, Docker startup and measured benchmarks are in [the project README](../README.md).

## Development

Docker Compose already runs the frontend. To run it directly on the host, stop the Compose frontend first and keep the backend/database/worker running:

```powershell
docker compose stop frontend
cd frontend
npm.cmd ci
npm.cmd run dev
```

The browser API URL defaults to `http://localhost:8000`; published production images build it as `/api` behind the same-origin gateway.

## Checks

```powershell
npm.cmd run lint
npm.cmd test
npm.cmd run build
npm.cmd run typecheck
npx.cmd playwright install chromium
npm.cmd run test:e2e
```

Playwright starts the production standalone server on port 3100 and mocks API responses for deterministic UI regression tests. Backend protocol/security/OCR integration is tested separately in CI. Browser traces and HTML reports are ignored by Git.

The document progress bar reflects actual queue/indexing state. Version metadata, document actions and progress states use shared light/dark theme tokens; desktop panels support pointer and keyboard resizing.
