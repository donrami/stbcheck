# STBcheck

A simple and elegant Stalker Portal checker and player. STBcheck allows you to bulk-check Stalker portals, discover channels, and stream content directly in your browser or through a proxy.

<img width="1916" height="1042" alt="image" src="https://github.com/user-attachments/assets/741ca7a7-f70f-400c-9d61-6f0021dcc645" />

## Features

- **Bulk Portal Handshake**: Authenticates with Stalker portals using lists of URLs and MAC addresses.
- **Channel Discovery**: Automatically fetches and categorizes channels from various portals.
- **Manual Verification**: Verify portals manually and keep a list of working servers.
- **Stream Proxy**: Proxies streams to bypass CORS and handle custom headers required by portals.

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

## License

GNU Affero General Public License v3.0. See `LICENSE` for the full license text.
