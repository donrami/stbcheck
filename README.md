# STBcheck

A Stalker Portal checker and player. STBcheck allows you to bulk-check Stalker portals, discover channels, and stream content directly in your browser.

<img width="1916" height="1042" alt="image" src="https://github.com/user-attachments/assets/741ca7a7-f70f-400c-9d61-6f0021dcc645" />

## Features

- **Bulk Portal Checking**: Paste a list of portal URLs and MAC addresses — the app extracts pairs, authenticates, and returns working portals with channel counts.
- **Channel Discovery**: Fetches and categorizes channels from each working portal.
- **Stream Proxy**: Proxies video streams to bypass CORS restrictions and handle portal-specific headers.
- **Logo Proxy**: Fetches and caches channel logos server-side to avoid mixed-content and CORS issues.
- **SSRF Protection**: Validates all outbound URLs and follows redirects safely to prevent server-side request forgery.
- **Rate Limiting**: Built-in rate limiting on all API endpoints to prevent abuse.
- **Security Headers**: Content Security Policy, X-Frame-Options, and other hardening headers on every response.
- **Circuit Breaker**: Automatic circuit breaker to prevent cascading failures when checking portals.
- **CLI Bulk Checker**: A standalone command-line tool (`stalker_checker.py`) for quick terminal-based portal checks.
- **Vercel Deployment**: Ready to deploy as a serverless function on Vercel.
- **Health Monitoring**: Built-in health check endpoint for monitoring and uptime checks.

## Quick Start

### Prerequisites

- Python 3.11+
- Git (for cloning)

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/donrami/stbcheck.git
   cd stbcheck
   ```

2. (Recommended) Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Run the application:
   ```bash
   python app.py
   ```

5. Open your browser and navigate to `http://localhost:6767`.

## Configuration

All settings are configurable via environment variables. Copy `.env.example` to `.env` and adjust as needed:

```bash
cp .env.example .env
```

### Configuration Options

| Category | Variable | Default | Description |
|----------|----------|---------|-------------|
| **Timeouts** | `REQUEST_TIMEOUT` | `10` | HTTP request timeout to portals (seconds) |
| | `STREAM_TIMEOUT` | `60` | Timeout for streaming operations (seconds) |
| | `LOGO_FETCH_TIMEOUT` | `15` | Timeout for fetching logo images (seconds) |
| **Deployment** | `VERCEL_COMPATIBLE_MODE` | `false` | Enable reduced timeouts for Vercel serverless (10s cap) |
| **Concurrency** | `MAX_CONCURRENT_PORTAL_CHECKS` | `15` | Max concurrent portal checks |
| **Logging** | `LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL) |
| | `LOG_FILE_MAX_BYTES` | `5242880` (5 MB) | Maximum log file size before rotation (bytes) |
| | `LOG_BACKUP_COUNT` | `2` | Number of backup log files to keep |
| **CORS** | `CORS_ORIGINS` | `http://localhost:6767,http://127.0.0.1:6767` | Allowed CORS origins (comma-separated) |
| **Server** | `SERVER_HOST` | `0.0.0.0` | Host to bind the server |
| | `SERVER_PORT` | `6767` | Port to bind the server |
| **Security** | `VERIFY_SSL` | `true` | Verify SSL certificates for outbound requests |
| **Application** | `APP_VERSION` | `1.0.1 - Playback Fixes` | Application version string |
| **Date Parsing** | `DATE_PARSING_TIMEZONE` | `UTC` | Timezone for parsing expiry dates |
| **Stalker Detection** | `STALKER_DETECTION_ENABLED` | `true` | Enable Stalker portal detection features |
| **Redis** | `REDIS_URL` | *(empty)* | Redis URL for shared logo cache across workers |
| **Cache** | `LOGO_CACHE_MAXSIZE` | `1000` | Maximum entries in logo cache |
| | `LOGO_CACHE_TTL` | `300` | TTL for logo cache entries (seconds) |
| | `STREAM_AUTH_CACHE_TTL` | `180` | Session auth cache TTL (seconds) |
| **Rate Limiting** | `RATE_LIMIT_PORTAL_CHECK` | `5/minute` | Rate limit for portal checking endpoint |
| | `RATE_LIMIT_PROXY_LOGO` | `2000/minute` | Rate limit for logo proxy endpoint |
| | `RATE_LIMIT_STREAM_OPS` | `60/minute` | Rate limit for streaming operations |
| **Streaming** | `STREAM_CHUNK_SIZE` | `131072` | Chunk size for streaming responses (bytes) |
| | `LOGO_CHUNK_SIZE` | `4096` | Chunk size for logo image transfers (bytes) |
| | `MAX_REDIRECTS` | `10` | Maximum number of redirects to follow for URL validation |
| **Circuit Breaker** | `CIRCUIT_BREAKER_THRESHOLD` | `10` | Failures before circuit opens |
| | `CIRCUIT_BREAKER_DURATION` | `30` | Seconds to keep circuit open |

## Deploying to Vercel

The project includes a `vercel.json` configuration and an `api/index.py` entry point for serverless deployment.

1. Install the Vercel CLI:
   ```bash
   npm i -g vercel
   ```

2. Deploy:
   ```bash
   vercel
   ```

Or connect your GitHub repository to Vercel for automatic deployments on push.

### Environment Variables on Vercel

Set the required environment variables in the Vercel project settings. All configuration options listed above are supported.

For Vercel deployments, set `VERCEL_COMPATIBLE_MODE=true` to enable reduced timeouts that work within serverless function limits.

## Architecture

STBcheck is built with **FastAPI** and follows a modular architecture:

```
stbcheck/
├── app.py                    # Thin entry point (runs uvicorn)
├── app/
│   ├── __init__.py
│   ├── main.py               # FastAPI app, middleware, routers
│   ├── config.py             # Active Pydantic settings (this is used)
│   ├── models.py            # Request/response models
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── portals.py        # Portal checking endpoints
│   │   └── streams.py        # Stream and logo proxy endpoints
│   └── services/
│       ├── __init__.py
│       ├── stalker_async.py  # Async Stalker portal client
│       ├── stalker.py       # Sync Stalker portal client (CLI)
│       ├── base.py          # Shared constants and utilities
│       ├── expiry.py        # Expiry detection logic
│       ├── date_utils.py    # Date parsing utilities
│       ├── url_validator.py # SSRF protection
│       ├── text_parser.py   # Input parsing utilities
│       └── stalker_detection.py  # Stalker portal detection
├── config.py                 # Legacy config (not used by app)
├── api/
│   └── index.py              # Vercel serverless entry point
├── stalker_checker.py        # Standalone CLI tool
├── requirements.txt          # Python dependencies
├── pytest.ini                # Pytest configuration
├── vercel.json               # Vercel deployment config
├── .env.example              # Configuration template
└── index.html                # Frontend interface
```

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Serves the main HTML interface |
| `/favicon.ico` | GET | Returns 204 (no content) |
| `/health` | GET | Health check endpoint (returns `{"status": "ok", "version": "..."}`) |
| `/api/check` | POST | Bulk portal checking with Server-Sent Events |
| `/api/get_link` | POST | Generate proxied stream link for a channel |
| `/api/check_stream` | GET | Check if a stream is accessible |
| `/api/proxy_stream` | GET | Proxy video stream content |
| `/api/proxy_logo` | GET | Proxy channel logo images (with caching) |

## CLI Bulk Checker

For quick terminal-based checks without the web UI:

```bash
python stalker_checker.py input.txt
```

Or paste text directly:

```bash
python stalker_checker.py
```

The CLI accepts input in various formats — labeled pairs, emoji-formatted blocks, or plain URL/MAC lists. It performs handshake, retrieves channel counts, and detects expiry dates.

## Running Tests

```bash
pytest
```

Run with markers to filter test types:

```bash
pytest -m unit          # Unit tests only (fast, isolated)
pytest -m integration   # Integration tests (may require external services)
pytest -m slow          # Slow running tests
```

The project follows a `tests/` directory structure mirroring the source code organization:

```
tests/
├── __init__.py
├── conftest.py
├── integration/
│   ├── __init__.py
│   └── test_api.py
└── unit/
    ├── __init__.py
    ├── test_base_cookies.py
    ├── test_config.py
    ├── test_handshake_404_fallback.py
    ├── test_headers.py
    ├── test_mac_normalization.py
    ├── test_models.py
    ├── test_stalker.py
    ├── test_stalker_detection.py
    ├── test_stream_health.py
    ├── test_token_refresh.py
    ├── test_utils.py
    └── test_verify_stream.py
```

## Security Features

- **SSRF Protection**: All outbound URLs are validated against private IP ranges and internal networks. Redirects are manually inspected to prevent SSRF via redirect chains.
- **Security Headers**: Responses include Content Security Policy (CSP), X-Content-Type-Options, X-Frame-Options, and Strict-Transport-Security (in production).
- **Rate Limiting**: All API endpoints are rate-limited using `slowapi` to prevent abuse.
- **Input Validation**: All inputs are validated via Pydantic models.
- **Circuit Breaker**: Automatic circuit breaker prevents cascading failures when portal checking experiences repeated errors.
- **Cache Control**: Sensitive operations do not cache responses, and logo caching is isolated per worker or shared via Redis.

## Caching Strategy

- **Logo Cache**: Logo images are cached using an in-memory TTLCache (default: 1000 entries, 5 min TTL). For multi-worker deployments (e.g., Vercel), enable Redis via `REDIS_URL` for shared caching.
- **Stream Auth Cache**: Session authentication is cached for 3 minutes (aligned with WAF token expiration).
- **Circuit Breaker State**: Failed portal checks are tracked per-portal; after 10 consecutive failures, the circuit "opens" for 30 seconds before allowing retries.

## Performance Considerations

- **Async Operations**: Portal checking uses `asyncio` and `aiohttp` for concurrent HTTP requests, with configurable concurrency limits (`MAX_CONCURRENT_PORTAL_CHECKS`).
- **Streaming**: Video streams are proxied in chunks (`STREAM_CHUNK_SIZE`) to minimize memory usage.
- **Logging**: Optional file logging with rotation (`LOG_FILE_MAX_BYTES`, `LOG_BACKUP_COUNT`); disabled on read-only filesystems (e.g., Vercel).
- **Vercel Mode**: Set `VERCEL_COMPATIBLE_MODE=true` for deployments that need to respect serverless function timeouts.

## License

GNU Affero General Public License v3.0. See `LICENSE` for the full license text.

## Contributing

Contributions are welcome. Please ensure that:
- All tests pass (`pytest`)
- Code follows the existing style (type hints, docstrings, formatting with `ruff`)
- New configuration options are added to `app/config.py` and documented in the README
- Security considerations are addressed (SSRF validation, rate limiting, etc.)
