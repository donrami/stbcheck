# Security Policy

## Reporting a Vulnerability

Please report security issues privately via [GitHub's private security advisories](https://github.com/donrami/stbcheck/security/advisories/new).

Do **not** open a public issue for security reports.

## Scope

In scope:

- The web API surface: proxy endpoints (`/api/proxy_stream`, `/api/proxy_logo`, `/api/get_link`, `/api/check_stream`)
- URL validation / SSRF protections (`app/services/url_validator.py`)
- Rate limiting bypasses (`app/limiter.py`)
- Security headers and input validation

Out of scope:

- Vulnerabilities in deployed instances you do not control
- Reports from automated scanners without a demonstrated impact

## Response Time

We aim to acknowledge reports within 7 days and provide a fix or mitigation within 90 days. Critical issues are prioritized.
