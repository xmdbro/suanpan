# suanpan 

A stateless, highly scalable counting API written in Python.

The front-facing documentation site is served at `/`. Interactive Swagger API
documentation remains available at `/docs`.

<!-- ## Quick Start

```bash
# 1. Clone and install
pip install -r requirements.txt

# 2. Configure (copy and edit)
cp .env.example .env

# 3. Run (requires a running Valkey/Redis instance)
uvicorn main:app --reload
```

Interactive docs are available at `http://localhost:8000/docs`. -->

## API Endpoints

All counters are scoped to a `{namespace}/{key}` pair. Namespaces and keys must be 3–64 characters: `[A-Za-z0-9_\-.]`.

### Public endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/hit/{namespace}/{key}` | Increment counter by 1 |
| `GET` | `/hit/{namespace}/{key}/shield` | Increment by 1 and return an SVG shield |
| `GET` | `/get/{namespace}/{key}` | Read current value |
| `GET` | `/get/{namespace}/{key}/shield` | Read current value as an SVG shield |
| `GET` | `/info/{namespace}/{key}` | Metadata: value, TTL, `is_genuine` |
| `POST` | `/create/{namespace}/{key}` | Create a managed counter; returns `admin_key` |
| `POST` | `/create` | Create with a randomly generated namespace + key |
| `GET` | `/healthcheck` | Valkey connectivity check |
| `GET` | `/stats` | Basic service statistics |

### Admin endpoints

Admin operations require the `admin_key` returned at creation time, passed as either:
- `?token=<key>` query param, or
- `Authorization: Bearer <key>` header

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/update/{namespace}/{key}` | Increment/decrement by `?value=N` |
| `POST` | `/set/{namespace}/{key}` | Overwrite with `?value=N` |
| `POST` | `/reset/{namespace}/{key}` | Reset to 0 |
| `POST` | `/delete/{namespace}/{key}` | Permanently delete |

### `is_genuine`

A counter is **genuine** when it has no admin key -- i.e. it was auto-created by a `/hit` call rather than explicitly via `/create`. Attempting an admin operation on a genuine counter returns `400`.

### TTL

All counters have a **6-month rolling TTL** refreshed on every `/hit`. Counters expire if untouched for ~6 months. (I believe this is reasonable)

### SVG shields

The `/get/.../shield` and `/hit/.../shield` endpoints are compatible with
Abacus shield URLs. The hit variant disables caching so each image request is
counted.

| Parameter | Default | Values |
|-----------|---------|--------|
| `bgcolor` | `007ec6` | 3- or 6-digit hex color, with or without `#` |
| `textcolor` | `fff` | 3- or 6-digit hex color, with or without `#` |
| `text` | `counter` | Left-hand label |
| `style` | `flat` | `flat`, `flat-square`, `plastic`, or a `-simple` variant |
| `fontsize` | `11` | Font size greater than 3 |
| `font` | `verdana` | Abacus font name, such as `arial` or `jetbrains-mono` |

Simple styles (`flat-simple`, `flat-square-simple`, and `plastic-simple`) only
show the counter value.

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `VALKEY_URL` | `valkey://localhost:6379` | Valkey connection URL |
| `PORT` | `8000` | HTTP port (set via uvicorn CLI) |

## Tests

Install the development dependencies and run the standard-library test suite:

```bash
pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

## Roadmap

- [x] Badges / shield endpoints (`/hit/{ns}/{key}/shield`, `/get/{ns}/{key}/shield`)
- [ ] JSONP support (`?callback=fn`)
- [ ] Server-Sent Events streaming (`/stream/{ns}/{key}`)
- [ ] Rate limiting (slowapi + Valkey backend)
- [ ] In-process GET micro-cache + TTL coalescing
- [ ] Prometheus metrics
- [x] Docker + CI/CD + Deployment
- [ ] Traffic trends (/history/{namespace}/{key}?range=7d&granularity=1d)
- [ ] Webhooks, potentially for milestone triggers (maybe)
- [ ] Namespace-wide hit & get (/batch/hit & /batch/get)
- [ ] Aggregation (/get/{namespace})
- [ ] Unique visitor counting using HLL (no change to counting behaviour)
- [x] Test suite
