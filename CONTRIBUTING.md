# Contributing

Thanks for contributing to STBcheck!

## Setup

```bash
git clone https://github.com/donrami/stbcheck.git
cd stbcheck
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

## Running Tests

```bash
pytest            # runs the suite defined in pytest.ini (tests/unit + tests/integration)
pytest -m unit    # fast, isolated tests only
```

Integration tests may require external services; failures there should be noted in your PR.

## Style

- Type hints on all function signatures.
- Format and lint with `ruff` (`ruff check . && ruff format .`).
- Docstrings on public functions and modules.
- Async code uses `asyncio`/`aiohttp`; keep blocking I/O out of async paths.

## Pull Requests

Please include:

1. A clear description of what changed and why.
2. Tests covering new behavior or bug fixes.
3. New config options added to `app/config.py` and documented in the README.
4. Security review for anything touching outbound requests: SSRF validation (`app/services/url_validator.py`) and rate limiting (`app/limiter.py`) must stay intact.
5. Updated README if behavior, endpoints, or configuration changed.
