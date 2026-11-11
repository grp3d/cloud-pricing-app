# Cloud Pricing Frontend

React, Vite and TypeScript web interface. It needs the backend running on `localhost:8000`;
Vite proxies `/api` to it.

```bash
npm install
npm run dev                  # :5173
npm test                     # unit tests (Vitest)
npm run test:e2e             # end-to-end tests (Playwright)
npm run lint && npm run build
npm run generate-api-types   # after a backend API change, with the backend running
```

Setup and tests in detail: [docs/development.md](../docs/development.md).
