# Cthulu UI Backend Server

This is a lightweight Flask server that exposes the local Cthulu system data (`cthulu.db` and logs) to the Web UI via a REST API.

## Prerequisites

- Python 3.10+
- Access to the Cthulu workspace (`C:\workspace\cthulu`)

## Installation

1. Navigate to this directory:
   ```powershell
   cd C:\workspace\cthulu\ui_server
   ```

2. Install dependencies:
   ```powershell
   pip install -r requirements.txt
   ```

## Usage

### Start the Server
Run the application directly with Python:
```powershell
python app.py
```
The server will start on **http://localhost:5000**.

### API Endpoints

- **GET /api/status**: Check connectivity.
- **GET /api/trades**: Retrieve recent trades from `cthulu.db`.
- **GET /api/logs**: Stream the last 100 lines from `out.log`.
- **GET /api/signals**: Real-time signals from the database.
- **GET /api/metrics**: System performance metrics.

## Troubleshooting

- **Database Locked**: SQLite might be busy if Cthulu is writing heavily. The server handles this gracefully but may return empty lists occasionally.
- **Port In Use**: If port 5000 is taken, edit the `app.run(port=5000)` line in `app.py`.
