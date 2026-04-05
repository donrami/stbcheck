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
- **CLI Bulk Checker**: A standalone command-line tool (`stalker_checker.py`) for quick terminal-based portal checks.
- **Vercel Deployment**: Ready to deploy as a serverless function on Vercel.

## Quick Start

### Prerequisites

- Python 3.8+

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/donrami/stbcheck.git
   cd stbcheck
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run the application:
   ```bash
   python app.py
   ```

4. Open your browser and navigate to `http://localhost:8000`.

## Configuration

All settings are configurable via environment variables. Copy `.env.example` to `.env` and adjust as needed:

```bash
cp .env.example .env
```

| Variable | Default | Description |
|---|---|---|
| `REQUEST_TIMEOUT` | `10` | HTTP request timeout to portals (seconds) |
| `STREAM_TIMEOUT` | `20` | Timeout for streaming operations (seconds) |
| `LOGO_FETCH_TIMEOUT` | `5` | Timeout for fetching logo images (seconds) |
| `MAX_CONCURRENT_PORTAL_CHECKS` | `15` | Max concurrent portal checks |
| `LOG_LEVEL` | `INFO` | Logging level |
| `CORS_ORIGINS` | `*` | Allowed CORS origins (comma-separated, or `*` for all) |
| `SERVER_HOST` | `0.0.0.0` | Host to bind the server |
| `SERVER_PORT` | `8000` | Port to bind the server |
| `VERIFY_SSL` | `true` | Verify SSL certificates for outbound requests |
| `REDIS_URL` | _(empty)_ | Redis URL for shared logo cache across workers |

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

## CLI Bulk Checker

For quick terminal-based checks without the web UI:

```bash
python stalker_checker.py input.txt
```

Or paste text directly:

```bash
python stalker_checker.py
```

Accepts input in various formats — labeled pairs, emoji-formatted blocks, or plain URL/MAC lists.

## Running Tests

```bash
pytest
```

Run with markers to filter test types:

```bash
pytest -m unit          # Unit tests only
pytest -m integration   # Integration tests only
```

## License

GNU Affero General Public License v3.0. See `LICENSE` for the full license text.
