---
title: DEPLOYING CTHULU
description: Production deployment strategies for Cthulu including Docker, Linux, Windows service, and monitoring setup
tags: [deployment, docker, production, monitoring]
sidebar_position: 9
version: 6.0.0
---

 ![](https://img.shields.io/badge/Version-6.0.0-4B0082?style=for-the-badge&labelColor=0D1117&logo=git&logoColor=white)
 ![Last Update](https://img.shields.io/badge/Last_Update-2026--01--06-4B0082?style=for-the-badge&labelColor=0D1117&logo=calendar&logoColor=white)
 ![](https://img.shields.io/github/last-commit/amuzetnoM/cthulu?branch=main&style=for-the-badge&logo=github&labelColor=0D1117&color=6A00FF)

## Table of Contents
- [Quick Start](#quick-start)
- [Docker Deployment](#docker-deployment)
- [Linux Deployment](#linux-deployment)
- [Windows Service](#windows-service)
- [Production Checklist](#production-checklist)
- [Monitoring Setup](#monitoring-setup)
- [Backup & Recovery](#backup--recovery)

---

## Quick Start

### Using Docker (Recommended)

The fastest way to deploy Cthulu is using Docker:

```bash
# 1. Clone repository
git clone https://github.com/amuzetnoM/Cthulu.git
cd Cthulu

# 2. Configure environment
cp .env.example .env
nano .env  # Edit with your MT5 credentials

# 3. Configure trading settings
cp config.example.json config.json
nano config.json  # Adjust risk settings

# 4. Start with Docker Compose
docker-compose up -d

# 5. View logs
docker-compose logs -f Cthulu

# 6. Access dashboards
# Grafana: http://localhost:3000 (admin/admin)
# Prometheus: http://localhost:9090
```

---

## Docker Deployment

### Prerequisites
- Docker 20.10+
- Docker Compose 2.0+
- 2GB RAM minimum
- 10GB disk space

### Step-by-Step Setup

#### 1. Build Custom Image

```bash
# Build image
docker build -t Cthulu:latest .

# Or build with specific version
docker build -t Cthulu:6.0.0 .
```

#### 2. Environment Configuration

Create `.env` file:

```bash
# MT5 Credentials
MT5_LOGIN=12345678
MT5_PASSWORD=your_password
MT5_SERVER=Broker-Demo

# Trading Settings
RISK_PER_TRADE=0.02
MAX_DAILY_LOSS=50
LOG_LEVEL=INFO
DRY_RUN=false

# Monitoring
GRAFANA_PASSWORD=secure_password_here
```

#### 3. Run Container

```bash
# Run with docker-compose (includes monitoring)
docker-compose up -d

# Or run standalone
docker run -d \
  --name Cthulu \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/config.json:/app/config.json:ro \
  -p 8181:8181 \
  Cthulu:latest
```

#### 4. Verify Deployment

```bash
# Check container status
docker ps

# View logs
docker logs Cthulu -f

# Check health
docker inspect Cthulu | grep -A 5 Health
```

### Docker Commands

```bash
# Start services
docker-compose up -d

# Stop services
docker-compose down

# Restart Cthulu only
docker-compose restart Cthulu

# View logs
docker-compose logs -f Cthulu

# Execute commands in container
docker-compose exec Cthulu python -m Cthulu --help

# Update to latest version
docker-compose pull
docker-compose up -d
```

### Scaling with Docker

```bash
# Run multiple instances with different symbols
docker run -d \
  --name Cthulu-eurusd \
  -e SYMBOL=EURUSD \
  -v $(pwd)/config-eurusd.json:/app/config.json:ro \
  Cthulu:latest

docker run -d \
  --name Cthulu-xauusd \
  -e SYMBOL=XAUUSD \
  -v $(pwd)/config-xauusd.json:/app/config.json:ro \
  Cthulu:latest
```

---

## Linux Deployment

### Using Systemd Service

#### 1. Install Dependencies

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install python3.12 python3-pip python3-venv

# CentOS/RHEL
sudo yum install python312 python3-pip
```

#### 2. Setup Application

```bash
# Create application directory
sudo mkdir -p /opt/Cthulu
sudo chown $USER:$USER /opt/Cthulu
cd /opt/Cthulu

# Clone repository
git clone https://github.com/amuzetnoM/Cthulu.git .

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies (skip MT5 on Linux)
grep -v "MetaTrader5" requirements.txt > requirements-linux.txt
pip install -r requirements-linux.txt

# Configure
cp config.example.json config.json
nano config.json
```

#### 3. Create Systemd Service

Create `/etc/systemd/system/Cthulu.service`:

```ini
[Unit]
Description=Cthulu Trading System
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=Cthulu
Group=Cthulu
WorkingDirectory=/opt/Cthulu
Environment="PATH=/opt/Cthulu/venv/bin"

# Environment variables from file
EnvironmentFile=/opt/Cthulu/.env

# Start command
ExecStart=/opt/Cthulu/venv/bin/python -m Cthulu \
    --config /opt/Cthulu/config.json \
    --skip-setup \
    --no-prompt \
    --log-level INFO

# Restart policy
Restart=on-failure
RestartSec=10s
StartLimitBurst=5
StartLimitIntervalSec=300

# Security settings
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/Cthulu/data /opt/Cthulu/logs

# Resource limits
MemoryLimit=1G
CPUQuota=200%

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=Cthulu

[Install]
WantedBy=multi-user.target
```

#### 4. Create Service User

```bash
# Create Cthulu user (no login)
sudo useradd -r -s /bin/false -d /opt/Cthulu Cthulu

# Set permissions
sudo chown -R Cthulu:Cthulu /opt/Cthulu
```

#### 5. Enable and Start Service

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable service
sudo systemctl enable Cthulu

# Start service
sudo systemctl start Cthulu

# Check status
sudo systemctl status Cthulu

# View logs
sudo journalctl -u Cthulu -f
```

### Service Management

```bash
# Start service
sudo systemctl start Cthulu

# Stop service
sudo systemctl stop Cthulu

# Restart service
sudo systemctl restart Cthulu

# Check status
sudo systemctl status Cthulu

# View logs (last 100 lines)
sudo journalctl -u Cthulu -n 100

# Follow logs in real-time
sudo journalctl -u Cthulu -f

# Check resource usage
systemctl show Cthulu --property=MemoryCurrent,CPUUsageNSec
```

---

## Windows Service

### Using NSSM (Non-Sucking Service Manager)

#### 1. Install NSSM

```powershell
# Download NSSM
Invoke-WebRequest -Uri "https://nssm.cc/release/nssm-2.24.zip" -OutFile "nssm.zip"
Expand-Archive -Path "nssm.zip" -DestinationPath "C:\tools"

# Add to PATH
$env:Path += ";C:\tools\nssm-2.24\win64"
```

#### 2. Install Service

```powershell
# Navigate to Cthulu directory
cd C:\workspace\Herald

# Install service
nssm install Cthulu "C:\workspace\Herald\venv\Scripts\python.exe" `
    "-m" "Cthulu" `
    "--config" "config.json" `
    "--skip-setup" `
    "--no-prompt"

# Set working directory
nssm set Cthulu AppDirectory "C:\workspace\Herald"

# Set environment variables
nssm set Cthulu AppEnvironmentExtra MT5_LOGIN=12345678 MT5_PASSWORD=your_password

# Configure restart policy
nssm set Cthulu AppExit Default Restart
nssm set Cthulu AppThrottle 5000
nssm set Cthulu AppRestartDelay 10000

# Configure logging
nssm set Cthulu AppStdout "C:\workspace\Herald\logs\stdout.log"
nssm set Cthulu AppStderr "C:\workspace\Herald\logs\stderr.log"

# Start service
nssm start Cthulu
```

#### 3. Service Management

```powershell
# Start service
nssm start Cthulu

# Stop service
nssm stop Cthulu

# Restart service
nssm restart Cthulu

# Check status
nssm status Cthulu

# Remove service
nssm remove Cthulu confirm
```

### Using Windows Task Scheduler (Alternative)

For non-service deployment, use Task Scheduler:

```powershell
# Create scheduled task
$action = New-ScheduledTaskAction `
    -Execute "C:\workspace\Herald\venv\Scripts\python.exe" `
    -Argument "-m Cthulu --config config.json --skip-setup --no-prompt" `
    -WorkingDirectory "C:\workspace\Herald"

$trigger = New-ScheduledTaskTrigger -AtStartup

$principal = New-ScheduledTaskPrincipal `
    -UserId "$env:USERNAME" `
    -LogonType ServiceAccount `
    -RunLevel Highest

Register-ScheduledTask `
    -TaskName "Cthulu Trading" `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Description "Herald autonomous trading system"
```

---

## Production Checklist

### Pre-Deployment

- [ ] Test on demo account for minimum 2 weeks
- [ ] Verify win rate meets expectations
- [ ] Validate position sizing calculations
- [ ] Test emergency shutdown procedure
- [ ] Review and adjust risk limits
- [ ] Backup configuration files
- [ ] Document broker-specific settings

### Infrastructure

- [ ] Dedicated server or VPS (2GB+ RAM)
- [ ] Reliable internet connection (fiber recommended)
- [ ] UPS for power backup
- [ ] Static IP or VPN for consistency
- [ ] Firewall rules configured
- [ ] SSL certificates for web interfaces

### Security

- [ ] Strong passwords for all services
- [ ] Enable 2FA where available
- [ ] Secure credential storage (.env file)
- [ ] Regular security updates
- [ ] Restricted file permissions
- [ ] API key rotation policy
- [ ] Audit logging enabled

### Monitoring

- [ ] Prometheus configured and running
- [ ] Grafana dashboards set up
- [ ] Alert rules configured
- [ ] Email/SMS notifications enabled
- [ ] Health check endpoints exposed
- [ ] Log aggregation configured
- [ ] Performance metrics tracked

### Backup & Recovery

- [ ] Automated database backups
- [ ] Configuration backups
- [ ] Recovery procedure documented
- [ ] Backup restoration tested
- [ ] Offsite backup storage
- [ ] Backup retention policy defined

---

## Monitoring Setup

### Prometheus Configuration

Already included in `monitoring/prometheus.yml`. Customize scrape intervals:

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'Cthulu'
    static_configs:
      - targets: ['Cthulu:8181']
    scrape_interval: 10s  # More frequent for trading
```

### Grafana Dashboards

Import pre-built dashboards:

1. Access Grafana: http://localhost:3000
2. Login (admin/admin)
3. Go to Dashboards → Import
4. Upload dashboard JSON from `monitoring/grafana/dashboards/`

Key dashboards:
- **Trading Overview**: P&L, positions, win rate
- **System Health**: CPU, memory, connection status
- **Risk Metrics**: Exposure, daily loss, position sizing
- **Performance**: Loop duration, API latency

### Alert Rules

Create `/opt/Cthulu/monitoring/alert_rules.yml`:

```yaml
groups:
  - name: Cthulu_alerts
    interval: 30s
    rules:
      - alert: HighDailyLoss
        expr: Cthulu_daily_pnl < -100
        for: 5m
        annotations:
          summary: "Daily loss exceeds threshold"
          
      - alert: ConnectionDown
        expr: up{job="Cthulu"} == 0
        for: 2m
        annotations:
          summary: "Cthulu connection lost"
          
      - alert: HighMemoryUsage
        expr: process_resident_memory_bytes > 1e9
        for: 10m
        annotations:
          summary: "Memory usage > 1GB"
```

---

## Backup & Recovery

### Automated Backup Script

Create `/opt/Cthulu/scripts/backup.sh`:

```bash
#!/bin/bash

# Configuration
BACKUP_DIR="/opt/Cthulu/backups"
RETENTION_DAYS=30
DATE=$(date +%Y%m%d_%H%M%S)

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Backup database
cp /opt/Cthulu/Cthulu.db "$BACKUP_DIR/Cthulu_${DATE}.db"

# Backup configuration
tar -czf "$BACKUP_DIR/config_${DATE}.tar.gz" \
    /opt/Cthulu/config.json \
    /opt/Cthulu/.env \
    /opt/Cthulu/configs/

# Backup logs (last 7 days)
find /opt/Cthulu/logs -name "*.log" -mtime -7 \
    -exec tar -czf "$BACKUP_DIR/logs_${DATE}.tar.gz" {} +

# Remove old backups
find "$BACKUP_DIR" -name "*.db" -mtime +$RETENTION_DAYS -delete
find "$BACKUP_DIR" -name "*.tar.gz" -mtime +$RETENTION_DAYS -delete

echo "Backup completed: $DATE"
```

Make executable and add to cron:

```bash
chmod +x /opt/Cthulu/scripts/backup.sh

# Add to crontab (daily at 2 AM)
crontab -e
0 2 * * * /opt/Cthulu/scripts/backup.sh >> /opt/Cthulu/logs/backup.log 2>&1
```

### Recovery Procedure

```bash
# 1. Stop Cthulu
sudo systemctl stop Cthulu

# 2. Restore database
cp /opt/Cthulu/backups/Cthulu_YYYYMMDD_HHMMSS.db /opt/Cthulu/Cthulu.db

# 3. Restore configuration
tar -xzf /opt/Cthulu/backups/config_YYYYMMDD_HHMMSS.tar.gz -C /

# 4. Verify permissions
sudo chown -R Cthulu:Cthulu /opt/Cthulu

# 5. Restart Cthulu
sudo systemctl start Cthulu

# 6. Verify
sudo systemctl status Cthulu
```

---

## Troubleshooting

### Common Issues

**Issue**: Service won't start
```bash
# Check logs
sudo journalctl -u Cthulu -n 50

# Verify Python environment
/opt/Cthulu/venv/bin/python --version

# Test configuration
/opt/Cthulu/venv/bin/python -m Cthulu --config config.json --help
```

**Issue**: High memory usage
```bash
# Check current usage
docker stats Cthulu

# Adjust memory limit in docker-compose.yml
services:
  Cthulu:
    mem_limit: 512m
```

**Issue**: Connection errors
```bash
# Test MT5 connection
python -c "from connector.mt5_connector import MT5Connector; print('OK')"

# Check network
ping your-broker-server.com

# Verify credentials
cat .env | grep MT5_
```

---

## Support & Updates

### Updating Cthulu

```bash
# Docker
docker-compose pull
docker-compose up -d

# Systemd
cd /opt/Cthulu
git pull
sudo systemctl restart Cthulu
```

### Getting Help

- Documentation: `/opt/Cthulu/docs/`
- Issues: https://github.com/amuzetnoM/Cthulu/issues
- Logs: `/opt/Cthulu/logs/Cthulu.log`

---

## Docker Image from GitHub Container Registry

### Pull Pre-built Image

The fastest way to get started - pull the official image from GHCR:

```bash
# Pull latest release
docker pull ghcr.io/amuzetnom/cthulu:latest

# Or specific version
docker pull ghcr.io/amuzetnom/cthulu:6.0.0

# Or major version
docker pull ghcr.io/amuzetnom/cthulu:5.2
```

### Run from GHCR Image

```bash
# 1. Create configuration
mkdir -p cthulu-config && cd cthulu-config
curl -O https://raw.githubusercontent.com/amuzetnoM/cthulu/main/config.example.json
curl -O https://raw.githubusercontent.com/amuzetnoM/cthulu/main/.env.example
mv config.example.json config.json
mv .env.example .env

# 2. Edit configuration
nano .env        # Add MT5 credentials
nano config.json # Adjust trading settings

# 3. Run container
docker run -d \
  --name cthulu \
  --env-file .env \
  -v $(pwd)/config.json:/app/config.json:ro \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/logs:/app/logs \
  -p 8181:8181 \
  --restart unless-stopped \
  ghcr.io/amuzetnom/cthulu:latest

# 4. View logs
docker logs -f cthulu
```

### Full Stack with Monitoring

```bash
# Clone for docker-compose.yml
git clone https://github.com/amuzetnoM/cthulu.git
cd cthulu

# Configure
cp .env.example .env && nano .env
cp config.example.json config.json && nano config.json

# Start full stack (Cthulu + Prometheus + Grafana)
docker-compose up -d

# Access
# - Cthulu RPC: http://localhost:8181
# - Prometheus: http://localhost:9090
# - Grafana: http://localhost:3000 (admin/admin)
```

### Available Tags

| Tag | Description |
|-----|-------------|
| `latest` | Latest stable release (6.0.0) |
| `6.0.0` | Specific version 6.0.0 |
| `6.0` | Current stable release |
| `5.1.0` | Previous version 5.1.0 |

---

**Last Updated**: January 2026  
**Version**: 6.0.0




