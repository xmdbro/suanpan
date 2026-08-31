# Suanpan documentation site

This directory is a dependency-free static frontend served by the main FastAPI
application. The site is available at `/`, while FastAPI's interactive Swagger
documentation remains available at `/docs`.

The examples use `window.location.origin`, so they automatically target the
same API in local development and production.

## Preview the complete application

Start the API from the repository root with its normal development command:

```bash
uvicorn main:app --reload
```

Then open:

- Site: `http://localhost:8000/`
- Swagger UI: `http://localhost:8000/docs`

The production Docker image copies this directory into `/app/docs`. No separate
static-site deployment or Vercel project is required.
