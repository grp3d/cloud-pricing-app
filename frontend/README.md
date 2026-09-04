# Cloud Pricing Frontend

React + Vite + TypeScript frontend for AWS Architecture Assembly & Pricing. See
`specs/001-assemble-price-aws-architecture/quickstart.md` for the full end-to-end validation
flow this UI implements.

## Setup

```bash
npm install
```

## Run

Requires the backend running at `http://localhost:8000` (see `backend/README.md`) — Vite
proxies `/api` to it (see `vite.config.ts`).

```bash
npm run dev
```

## Regenerate API types

The frontend's request/response types are generated from the backend's live OpenAPI schema —
never hand-maintained (Constitution Principle IV: contract drift must fail a build, not surface
as a runtime bug):

```bash
npm run generate-api-types   # backend must be running at localhost:8000
npm run check-api-types      # regenerates and fails if the checked-in file would change — the CI gate
```

## Test / Build / Lint

```bash
npm test
npm run build   # tsc -b && vite build
npm run lint
```
