# STBcheck

A powerful and elegant Stalker Portal checker and player. **STBcheck** allows you to analyze Stalker portals, discover channels, and stream content directly in your browser or through a proxy.

## Features

- **Portal Handshake**: Authenticates with Stalker portals using MAC addresses.
- **Channel Discovery**: Automatically fetches and categorizes channels from various portals.
- **Manual Verification**: Verify portals manually and keep a list of working servers.
- **Stream Proxy**: Proxies streams to bypass CORS and handle custom headers required by portals.
- **Modern UI**: A sleek, dark-themed responsive interface built with modern CSS and JavaScript.
- **Security Focused**: Includes SSRF protection and safe URL handling for proxying.

## Quick Start

### Prerequisites

- Python 3.8+
- `fastapi`
- `uvicorn`
- `requests`

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/donrami/stbcheck.git
   cd stbcheck
   ```

2. Install dependencies:
   ```bash
   pip install fastapi uvicorn requests
   ```

3. Run the application:
   ```bash
   python app.py
   ```

4. Open your browser and navigate to `http://localhost:8000`.

## Security

STBcheck includes built-in security measures to protect the host:
- **SSRF Protection**: Validates and restricts proxied URLs to prevent Server-Side Request Forgery.
- **Safe Protocol Handling**: Only allows `http` and `https` schemes for external requests.
- **Private Network Blocking**: Automatically blocks requests to localhost and private IP ranges.

## License

MIT License. See `LICENSE` for more information.
