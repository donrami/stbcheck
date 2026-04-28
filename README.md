# STBcheck

A Stalker portal checker and player — bulk-check portals, discover channels, and stream content in your browser.

<img width="1916" height="1042" alt="STBcheck interface screenshot" src="https://github.com/user-attachments/assets/741ca7a7-f70f-400c-9d61-6f0021dcc645" />

---

## Table of Contents

- [Quick Start](#quick-start)
- [Features](#features)
- [Usage](#usage)
  - [Web Interface](#web-interface)
  - [CLI Bulk Checker](#cli-bulk-checker)
  - [API Endpoints](#api-endpoints)
- [Configuration](#configuration)
- [Architecture](#architecture)
- [Deployment](#deployment)
- [Security](#security)
- [Performance](#performance)
- [Contributing](#contributing)
- [License](#license)

---

## Quick Start

```bash
git clone https://github.com/donrami/stbcheck.git
cd stbcheck
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open [http://localhost:6767](http://localhost:6767) in your browser.

> **Prerequisites**: Python 3.11+ and Git.

---

## Features

- **Bulk Portal Checking** — paste URLs and MAC addresses; the app extracts pairs, authenticates, and returns working portals with channel counts.
- **Channel Discovery** — fetches and categorizes channels from each working portal.
- **Stream & Logo Proxy** — proxies video streams (bypasses CORS) and caches channel logos server-side.
- **SSRF Protection** — validates all outbound URLs, inspects redirect chains to prevent server-side request forgery.
- **Circuit Breaker** — prevents cascading failures when portal checking encounters repeated errors.
- **Rate Limiting** — built-in limits on all API endpoints.
- **Security Headers** — CSP, X-Frame-Options, and other hardening headers on every response.
- **Health Monitoring** — `/health` endpoint for uptime checks.
- **CLI Bulk Checker** — standalone `stalker_checker.py` for quick terminal-based portal checks.
- **Vercel-ready** — deploy as a serverless function with the included `vercel.json`.

---

## Usage

### Web Interface

Open [http://localhost:6767](http://localhost:6767) for the full UI: paste portals, start discovery, browse channels, and watch streams.

### CLI Bulk Checker

For a quick terminal check without the web UI:

```bash
python stalker_checker.py input.txt
```

Or paste text interactively:

```bash
python stalker_checker.py
```

The CLI accepts labeled pairs, emoji-formatted blocks, or plain URL/MAC lists. It performs handshake, retrieves channel counts, and detects expiry dates.

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Serves the main HTML interface |
| `/favicon.ico` | GET | Returns 204 (no content) |
| `/health` | GET | Health check — returns `{"status": "ok", "version": "..."}` |
| `/api/check` | POST | Bulk portal checking with Server-Sent Events |
| `/api/get_link` | POST | Generate a proxied stream link for a channel |
| `/api/check_stream` | GET | Check if a stream is accessible |
| `/api/proxy_stream` | GET | Proxy video stream content |
| `/api/proxy_logo` | GET | Proxy channel logo images (with caching) |

---

## Configuration

Copy `.env.example` to `.env` and adjust as needed:

```bash
cp .env.example .env
```

All settings are environment variables, grouped by category below.

### Timeouts

| Variable | Default | Description |
|----------|---------|-------------|
| `REQUEST_TIMEOUT` | `10` | HTTP request timeout to portals (seconds) |
| `STREAM_TIMEOUT` | `60` | Timeout for streaming operations (seconds) |
| `LOGO_FETCH_TIMEOUT` | `15` | Timeout for fetching logo images (seconds) |

### Server & CORS

| Variable | Default | Description |
|----------|---------|-------------|
| `SERVER_HOST` | `0.0.0.0` | Host to bind the server |
| `SERVER_PORT` | `6767` | Port to bind the server |
| `CORS_ORIGINS` | `http://localhost:6767,http://127.0.0.1:6767` | Allowed CORS origins (comma-separated) |
| `APP_VERSION` | `1.1.0` | Application version string |

### Concurrency & Logging

| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_CONCURRENT_PORTAL_CHECKS` | `15` | Max concurrent portal checks |
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL) |
| `LOG_FILE_MAX_BYTES` | `5242880` (5 MB) | Max log file size before rotation |
| `LOG_BACKUP_COUNT` | `2` | Number of backup log files to keep |

### Caching

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | *(empty)* | Redis URL for shared logo cache across workers |
| `LOGO_CACHE_MAXSIZE` | `1000` | Max entries in logo cache |
| `LOGO_CACHE_TTL` | `300` | TTL for logo cache entries (seconds) |
| `STREAM_AUTH_CACHE_TTL` | `180` | Session auth cache TTL (seconds) |

### Rate Limiting

| Variable | Default | Description |
|----------|---------|-------------|
| `RATE_LIMIT_PORTAL_CHECK` | `5/minute` | Rate limit for portal checking endpoint |
| `RATE_LIMIT_PROXY_LOGO` | `2000/minute` | Rate limit for logo proxy endpoint |
| `RATE_LIMIT_STREAM_OPS` | `60/minute` | Rate limit for streaming operations |

### Streaming

| Variable | Default | Description |
|----------|---------|-------------|
| `STREAM_CHUNK_SIZE` | `131072` | Chunk size for streaming responses (bytes) |
| `LOGO_CHUNK_SIZE` | `4096` | Chunk size for logo image transfers (bytes) |
| `MAX_REDIRECTS` | `10` | Max redirects to follow for URL validation |

### Circuit Breaker

| Variable | Default | Description |
|----------|---------|-------------|
| `CIRCUIT_BREAKER_THRESHOLD` | `10` | Failures before circuit opens |
| `CIRCUIT_BREAKER_DURATION` | `30` | Seconds to keep circuit open |

### Security & Detection

| Variable | Default | Description |
|----------|---------|-------------|
| `VERIFY_SSL` | `true` | Verify SSL certificates for outbound requests |
| `STALKER_DETECTION_ENABLED` | `true` | Enable Stalker portal detection features |

### Date Parsing

| Variable | Default | Description |
|----------|---------|-------------|
| `DATE_PARSING_TIMEZONE` | `UTC` | Timezone for parsing expiry dates |

### Vercel Deployment

| Variable | Default | Description |
|----------|---------|-------------|
| `VERCEL_COMPATIBLE_MODE` | `false` | Enable reduced timeouts for serverless (10s cap) |

---

## Architecture

The application is built with **FastAPI** and follows a modular layout:

```
stbcheck/
├── app.py                        # Entry point (runs uvicorn)
├── api/index.py                  # Vercel serverless entry point
├── app/
│   ├── main.py                   # FastAPI app, middleware, routers
│   ├── config.py                 # Pydantic settings (active config)
│   ├── models.py                 # Request/response models
│   ├── routers/
│   │   ├── portals.py            # Portal checking endpoints
│   │   └── streams.py            # Stream & logo proxy endpoints
│   └── services/
│       ├── stalker_async.py      # Async Stalker portal client
│       ├── stalker.py            # Sync Stalker portal client (CLI)
│       ├── base.py               # Shared constants & utilities
│       ├── expiry.py             # Expiry detection logic
│       ├── date_utils.py         # Date parsing utilities
│       ├── url_validator.py      # SSRF protection
│       ├── text_parser.py        # Input parsing utilities
│       └── stalker_detection.py  # Stalker portal detection
├── stalker_checker.py            # Standalone CLI tool
├── config.py                     # Legacy config (not used by app)
├── index.html                    # Frontend interface
├── requirements.txt
├── pytest.ini
├── vercel.json
└── .env.example
```

---

## Deployment

### Vercel

The project includes a `vercel.json` config and `api/index.py` entry point for serverless deployment.

```bash
npm i -g vercel
vercel
```

Or connect your GitHub repository to Vercel for automatic deploys.

Set environment variables in the Vercel project settings. For serverless deployments, enable `VERCEL_COMPATIBLE_MODE=true` to cap timeouts within function limits.

---

## Security

- **SSRF Protection** — all outbound URLs validated against private IP ranges; redirect chains inspected to prevent SSRF via redirects.
- **Security Headers** — CSP, X-Content-Type-Options, X-Frame-Options, and Strict-Transport-Security (in production).
- **Rate Limiting** — all endpoints rate-limited via `slowapi`.
- **Input Validation** — all inputs validated through Pydantic models.
- **Circuit Breaker** — prevents cascading failures during repeated portal errors.
- **Cache Control** — sensitive operations do not cache responses; logo caching is isolated per worker or shared via Redis.

---

## Performance

- **Async I/O** — portal checking uses `asyncio` and `aiohttp` with configurable concurrency (`MAX_CONCURRENT_PORTAL_CHECKS`).
- **Streaming** — video streams are proxied in chunks (`STREAM_CHUNK_SIZE`) to minimize memory.
- **Logging** — optional file rotation (`LOG_FILE_MAX_BYTES`, `LOG_BACKUP_COUNT`); automatically disabled on read-only filesystems (e.g., Vercel).
- **Logo Cache** — in-memory TTLCache (1000 entries, 5 min TTL). For multi-worker deployments, share via `REDIS_URL`.
- **Stream Auth Cache** — session authentication cached for 3 minutes (aligned with WAF token expiration).
- **Circuit Breaker** — after 10 consecutive failures per portal, the circuit opens for 30 seconds before allowing retries.
- **Vercel Mode** — set `VERCEL_COMPATIBLE_MODE=true` to respect serverless function timeouts.

---

## Contributing

Contributions welcome. Please ensure:

- All tests pass (`pytest`)
- Code follows existing style (type hints, docstrings, `ruff` formatting)
- New config options are added to `app/config.py` and documented here
- Security considerations are addressed (SSRF validation, rate limiting, etc.)

---

## License

GNU Affero General Public License v3.0. See [LICENSE](LICENSE) for the full text.
