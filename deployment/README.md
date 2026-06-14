# Cthulu GCP Deployment
> **Version**: v6.0.0  
> **Last Updated**: 2026-01-02  
> **Status**: LIVE

---

## 1. Infrastructure Overview

### Google Cloud Platform Details
| Property | Value |
|----------|-------|
| **Project** | Your GCP Project |
| **VM Name** | `cthulu-reign-node` |
| **Region/Zone** | `us-central1-a` |
| **Machine Type** | `n2-standard-2` (Spot Instance) |
| **OS** | Windows 11 (via dockur/windows container) |
| **External IP** | `34.171.231.16` |
| **Web Desktop** | http://34.171.231.16:8006 |
| **VS Code Server** | http://34.171.231.16:8080 (if installed) |

### Cost Optimization
- **Spot VM**: ~70% cheaper than standard. May be preempted if GCP needs capacity.
- **Persistent Disk**: Data survives preemption. Only lost if explicitly deleted.
- **Auto-Restart**: Configure via GCP Console or `gcloud` to restart after preemption.

---

## 2. Accessing the VM

### Method 1: Web Desktop (Primary)
1. Open browser: http://34.171.231.16:8006
2. Wait 30-60 seconds for Windows to load
3. Click inside the screen to interact
4. Full Windows 11 desktop available

### Method 2: SSH via gcloud CLI
```powershell
# From your local machine with gcloud installed
gcloud compute ssh cthulu-reign-node --zone=us-central1-a
```

### Method 3: RDP (Remote Desktop)
```
Address: 34.171.231.16:3389
Username: (Windows user you create)
Password: (Windows password you set)
```

### Method 4: VS Code Server (After Setup)
1. Navigate to: http://34.171.231.16:8080
2. Enter password if configured
3. Full VS Code in browser

---

## 3. First-Time Setup (Fresh VM)

### Step 1: Access the VM
1. Go to http://34.171.231.16:8006
2. Complete Windows initial setup if prompted
3. Open PowerShell **as Administrator**

### Step 2: Run the Setup Script
**Option A - If you have the script file locally:**
1. Download `SETUP.ps1` from this directory
2. Copy entire contents
3. Paste into PowerShell Admin window
4. Press Enter

**Option B - Direct from GitHub (after push):**
```powershell
Set-ExecutionPolicy Bypass -Scope Process -Force
irm https://raw.githubusercontent.com/amuzetnoM/cthulu/main/deployment/SETUP.ps1 | iex
```

### Step 3: What the Script Installs
- ✅ Chocolatey (package manager)
- ✅ Python 3.10
- ✅ Git
- ✅ VS Code
- ✅ MetaTrader 5
- ✅ Cthulu repository (cloned to `C:\workspace\cthulu`)
- ✅ Python virtual environment with dependencies
- ✅ Desktop shortcuts

### Step 4: Configure MT5
1. Launch MetaTrader 5
2. Login with your broker credentials
3. **Enable Algo Trading**: Tools → Options → Expert Advisors → ☑ Allow algorithmic trading
4. **Enable DLL**: Tools → Options → Expert Advisors → ☑ Allow DLL imports

### Step 5: Configure Cthulu
Edit `C:\workspace\cthulu\config.json`:
```json
{
    "mt5": {
        "login": YOUR_LOGIN_NUMBER,
        "password": "YOUR_PASSWORD",
        "server": "YOUR_BROKER_SERVER"
    },
    "trading": {
        "symbol": "BTCUSD#",
        "mindset": "dynamic",
        "timeframe": "M5"
    }
}
```

### Step 6: Launch Cthulu
Double-click **"Cthulu Wizard.bat"** on Desktop, or:
```powershell
cd C:\workspace\cthulu
.\venv\Scripts\Activate.ps1
python __main__.py --wizard
```

---

## 4. VM Management Commands

### Start/Stop VM (from local machine)
```powershell
# Start
gcloud compute instances start cthulu-reign-node --zone=us-central1-a

# Stop (saves cost when not trading)
gcloud compute instances stop cthulu-reign-node --zone=us-central1-a

# Check status
gcloud compute instances describe cthulu-reign-node --zone=us-central1-a --format="value(status)"
```

### Get Current External IP
```powershell
gcloud compute instances describe cthulu-reign-node --zone=us-central1-a --format="value(networkInterfaces[0].accessConfigs[0].natIP)"
```

### SSH Tunnel for Secure Access
```powershell
# Forward local port 8006 to VM's 8006
gcloud compute ssh cthulu-reign-node --zone=us-central1-a -- -L 8006:localhost:8006 -N
# Then access via http://localhost:8006
```

### Reset Windows Password (if locked out)
```powershell
gcloud compute reset-windows-password cthulu-reign-node --zone=us-central1-a
```

---

## 5. File System Layout (on VM)

```
C:\
├── workspace\
│   ├── cthulu\          # Main trading system
│   │   ├── config.json  # YOUR TRADING CONFIG
│   │   ├── venv\        # Python environment
│   │   └── ...
│   └── sentinel\        # Crash recovery monitor
│
├── Program Files\
│   └── MetaTrader 5\    # MT5 installation
│
└── Users\<user>\Desktop\
    ├── Cthulu Wizard.bat    # Launch wizard
    ├── Cthulu Launch.bat    # Direct launch
    └── Sentinel Monitor.bat # Crash recovery
```

---

## 6. Troubleshooting

### VM Won't Start
```powershell
# Check quota
gcloud compute regions describe us-central1 --format="value(quotas)"

# Try different zone
gcloud compute instances move cthulu-reign-node --zone=us-central1-a --destination-zone=us-central1-b
```

### Can't Access Web Desktop (Port 8006)
1. Check firewall: GCP Console → VPC Network → Firewall → Ensure port 8006 is open
2. Check VM status: Must be RUNNING
3. Wait 2-3 minutes after VM start for Windows to boot

### MT5 Won't Connect
1. Check internet inside VM
2. Verify broker server name
3. Try different broker servers from your broker's list

### Cthulu Errors
```powershell
# Check logs
Get-Content C:\workspace\cthulu\logs\cthulu.log -Tail 50

# Reinstall dependencies
cd C:\workspace\cthulu
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt --force-reinstall
```

### Spot VM Preempted
- This is normal for Spot instances
- Just restart: `gcloud compute instances start cthulu-reign-node --zone=us-central1-a`
- Consider scheduled restarts or use Sentinel for auto-recovery

---

## 7. Security Notes

- **Firewall**: Only ports 8006 (web desktop), 8080 (VS Code), 3389 (RDP) should be open
- **Secrets**: Never commit `config.json` with credentials to Git
- **Access**: Consider IP whitelisting in GCP Firewall for your IP only
- **Cost**: Stop VM when not trading to avoid charges

---

## 8. Quick Reference

| Task | Command/URL |
|------|-------------|
| Access Desktop | http://34.171.231.16:8006 |
| Start VM | `gcloud compute instances start cthulu-reign-node --zone=us-central1-a` |
| Stop VM | `gcloud compute instances stop cthulu-reign-node --zone=us-central1-a` |
| Launch Cthulu | Double-click `Cthulu Wizard.bat` on VM Desktop |
| View Logs | `C:\workspace\cthulu\logs\` |
| Edit Config | `C:\workspace\cthulu\config.json` |

---

**This document is the single source of truth for GCP deployment.**
