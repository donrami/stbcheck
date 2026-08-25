# STBcheck

[![License: AGPL-3.0](https://img.shields.io/github/license/donrami/stbcheck)](https://www.gnu.org/licenses/agpl-3.0)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![CI](https://github.com/donrami/stbcheck/actions/workflows/ci.yml/badge.svg)](https://github.com/donrami/stbcheck/actions)

A Stalker portal checker and player: bulk-check portals, discover channels, and stream content in your browser.

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
  - [Common Settings](#common-settings)
  - [Full Reference](#full-reference)
- [Deployment](#deployment)
  - [Local Development](#local-development)
  - [Vercel](#vercel)
- [Troubleshooting](#troubleshooting)
- [Architecture](#architecture)
- [Security](#security)
- [Performance](#performance)
- [Contributing](#contributing)
- [Lawful Use](#lawful-use)
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
>
> **Windows**: activate the venv with `venv\Scripts\activate` instead of `source venv/bin/activate`.

---

## Features

- **Bulk portal checking**: paste URLs and MAC addresses; the app extracts pairs, authenticates against each portal, and reports the working ones with channel counts.
- **Channel discovery**: pulls channels from every working portal and sorts them into categories.
- **Stream and logo proxy**: video streams go through the server (which sidesteps CORS), and channel logos are cached in memory with a TTL.
- **SSRF protection**: every outbound URL is validated and redirect chains are inspected, so nothing can be tricked into reaching internal addresses.
- **Rate limiting**: all API endpoints are throttled out of the box (via `slowapi`).
- **Security headers**: CSP, X-Frame-Options, and other hardening headers on every response.
- **Health monitoring**: `/health` endpoint for uptime checks.
- **CLI bulk checker**: standalone `stalker_checker.py` for quick terminal-based portal checks.
- **Vercel-ready**: deploy as a serverless function with the included `vercel.json`.

---

## Usage

### Web Interface

Open [http://localhost:6767](http://localhost:6767) for the full UI: paste portals, start discovery, browse channels, and watch streams.

### CLI Bulk Checker

For a quick terminal check without the web UI:

```bash
python stalker_checker.py input.txt
```

Or pipe a file / paste text interactively:

```bash
cat list.txt | python stalker_checker.py
python stalker_checker.py
```

The CLI accepts labeled pairs, emoji-formatted blocks, or plain URL/MAC lists. It performs the portal handshake, reports status, and detects expiry dates. (Channel counts are only available through the web API.)

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Serves the main HTML interface |
| `/favicon.ico` | GET | Returns 204 (no content) |
| `/health` | GET | Health check returning `{"status": "ok", "version": "..."}` |
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

All settings are environment variables; defaults below come from `app/config.py`.

### Common Settings

Most deployments only need these:

| Variable | Default | Description |
|----------|---------|-------------|
| `SERVER_PORT` | `6767` | Port to bind the server |
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL) |
| `CORS_ORIGINS` | `http://localhost:6767,http://127.0.0.1:6767` | Allowed CORS origins (comma-separated) |
| `VERIFY_SSL` | `true` | Verify SSL certificates for outbound requests (disable only for testing with self-signed certs) |
| `RATE_LIMIT_PORTAL_CHECK` | `5/minute` | Rate limit for portal checking endpoint |

### Full Reference

#### Timeouts

| Variable | Default | Description |
|----------|---------|-------------|
| `REQUEST_TIMEOUT` | `10` | HTTP request timeout to portals (seconds) |
| `STREAM_TIMEOUT` | `60` | Timeout for streaming operations (seconds) |
| `LOGO_FETCH_TIMEOUT` | `15` | Timeout for fetching logo images (seconds) |

#### Server & App

| Variable | Default | Description |
|----------|---------|-------------|
| `SERVER_HOST` | `0.0.0.0` | Host to bind the server |
| `APP_VERSION` | `1.1.0` | Application version string |

Variables from [Common Settings](#common-settings) are not repeated here.

#### Concurrency & Logging

| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_CONCURRENT_PORTAL_CHECKS` | `15` | Max concurrent portal checks |
| `LOG_FILE_MAX_BYTES` | `5242880` (5 MB) | Max log file size before rotation |
| `LOG_BACKUP_COUNT` | `2` | Number of backup log files to keep |

#### Caching

| Variable | Default | Description |
|----------|---------|-------------|
| `LOGO_CACHE_MAXSIZE` | `1000` | Maximum number of entries in the logo cache |
| `LOGO_CACHE_TTL` | `300` | Time-to-live for logo cache entries (seconds) |
| `STREAM_AUTH_CACHE_TTL` | `180` | Session auth cache TTL (seconds) |

#### Rate Limiting

| Variable | Default | Description |
|----------|---------|-------------|
| `RATE_LIMIT_PROXY_LOGO` | `2000/minute` | Rate limit for logo proxy endpoint |
| `RATE_LIMIT_STREAM_OPS` | `60/minute` | Rate limit for streaming operations |

#### Streaming

| Variable | Default | Description |
|----------|---------|-------------|
| `STREAM_CHUNK_SIZE` | `131072` | Chunk size for streaming responses (bytes) |
| `LOGO_CHUNK_SIZE` | `4096` | Chunk size for logo image transfers (bytes) |
| `MAX_REDIRECTS` | `10` | Max redirects to follow when proxying streams |

#### Security & Detection

| Variable | Default | Description |
|----------|---------|-------------|
| `X_USER_AGENT` | `model=MAG250;version=218;sig=6fb2447331356ecca928394477c0500e2630cc3c` | `X-User-Agent` header sent to portals; some WAFs whitelist-match the canonical `Model: MAG250; Link: WiFi` format instead |

#### Date Parsing

| Variable | Default | Description |
|----------|---------|-------------|
| `DATE_PARSING_TIMEZONE` | `UTC` | Timezone for parsing expiry dates |

---

## Deployment

### Local Development

The Quick Start steps above are all you need for development or self-hosting on a VPS. Run `python app.py`; uvicorn binds to `SERVER_HOST:SERVER_PORT`.

> No Docker image or systemd unit ships with this repo. If you deploy that way, containerize the app yourself or run it under a process manager of your choice.

### Vercel

The project includes a `vercel.json` config and `api/index.py` entry point for serverless deployment.

```bash
npm i -g vercel
vercel
```

Or connect your GitHub repository to Vercel for automatic deploys.

Set environment variables in the Vercel project settings. For serverless deployments, enable `VERCEL_COMPATIBLE_MODE=true` to cap timeouts within function limits. Long-lived video streams fit serverless functions poorly; prefer a VPS for heavy streaming use.

---

## Troubleshooting

- **Port already in use**: change `SERVER_PORT` or stop the other process bound to 6767.
- **SSL certificate errors on portal checks**: a portal may use a self-signed cert. Set `VERIFY_SSL=false` only if you understand the risk.
- **Rate limit (429) responses**: lower traffic or adjust the `RATE_LIMIT_*` variables.
- **Streams fail after ~60s**: probably `STREAM_TIMEOUT`. Raise it, or check that the portal itself is healthy.
- **Vercel function timeout errors**: enable `VERCEL_COMPATIBLE_MODE=true`; heavy streams still belong on a VPS.
- **Log file not created on Vercel**: expected. File logging is disabled automatically on read-only filesystems.

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
│   ├── limiter.py                # slowapi rate limiting setup
│   ├── models.py                 # Request/response models
│   ├── routers/
│   │   ├── portals.py            # Portal checking endpoints
│   │   └── streams.py            # Stream & logo proxy endpoints
│   └── services/
│       ├── stalker_async.py      # Async Stalker portal client
│       ├── base.py               # Shared constants & utilities
│       ├── expiry.py             # Expiry detection logic
│       ├── date_utils.py         # Date parsing utilities
│       ├── url_validator.py      # SSRF protection
│       ├── text_parser.py        # Input parsing utilities
│       └── stalker_detection.py  # Stalker portal detection
├── tests/
│   ├── unit/                     # Unit tests
│   └── integration/              # Integration tests
├── stalker_checker.py            # Standalone CLI tool
├── index.html                    # Frontend interface
├── requirements.txt
├── pytest.ini
├── vercel.json
└── .env.example
```

---

## Security

- **SSRF protection**: all outbound URLs are validated against private IP ranges (`app/services/url_validator.py`), and redirect chains are inspected so a redirect can't be used to reach internal addresses.
- **Security headers**: CSP, X-Content-Type-Options, X-Frame-Options, and Strict-Transport-Security (in production).
- **Rate limiting**: every endpoint is throttled via `slowapi` (`app/limiter.py`).
- **Input validation**: requests are validated through Pydantic models.
- **Cache control**: sensitive operations never cache responses, and the logo cache lives per-process in memory only.

---

## Performance

- **Async I/O**: portal checking runs on `asyncio` and `aiohttp`, with concurrency capped by `MAX_CONCURRENT_PORTAL_CHECKS`.
- **Streaming**: video is proxied in chunks (`STREAM_CHUNK_SIZE`) to keep memory flat.
- **Logging**: optional file rotation (`LOG_FILE_MAX_BYTES`, `LOG_BACKUP_COUNT`); disabled automatically on read-only filesystems like Vercel.
- **Logo cache**: in-memory TTLCache (default 1000 entries, 5 min TTL), kept per worker process. Each worker has its own.
- **Stream auth cache**: session authentication is cached for 3 minutes, aligned with WAF token expiration.
- **Vercel mode**: set `VERCEL_COMPATIBLE_MODE=true` to respect serverless function timeouts.

---

## Contributing

Contributions welcome. See [CONTRIBUTING.md](CONTRIBUTING.md); the short version:

- All tests pass (`pytest`)
- Code follows existing style (type hints, docstrings, `ruff` formatting)
- New config options are added to `app/config.py` and documented here
- Security considerations are addressed (SSRF validation, rate limiting, etc.)

---

## Lawful Use

This software is provided for legitimate IPTV management and diagnostic purposes only. Users are responsible for ensuring they have proper authorization from service providers for any portals they check or streams they access. The authors and contributors assume no liability for misuse of this software. Streaming copyrighted content without proper licensing may violate local laws.

---

## License

GNU Affero General Public License v3.0. See [LICENSE](LICENSE) for the full text.
