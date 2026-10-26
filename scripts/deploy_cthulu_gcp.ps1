# Cthulu GCloud Deployment Script
# This script automates the creation of an "Almost Free" Windows environment on GCP.

$VM_NAME = "cthulu-reign-node"
$ZONE = "us-central1-a"
$MACHINE_TYPE = "n2-standard-2" # Required for Nested Virtualization
$DISK_SIZE = "50GB"

# 1. Create the Startup Script (Automation for the Linux Host)
$STARTUP_SCRIPT = @"
#! /bin/bash
sudo apt-get update
sudo apt-get install -y docker.io
sudo systemctl start docker
sudo systemctl enable docker

# Run the Windows Container (dockur/windows)
# This will pull the official Windows ISO and run it via KVM
sudo docker run -d \
    --name cthulu-windows \
    --restart always \
    -p 8006:8006 \
    --device=/dev/kvm \
    --cap-add NET_ADMIN \
    -e RAM_SIZE=6G \
    -e CPU_CORES=2 \
    dockurr/windows
"@

# Save startup script temporarily
$STARTUP_FILE = "$env:TEMP\cthulu_startup.sh"
$STARTUP_SCRIPT | Out-File -FilePath $STARTUP_FILE -Encoding ascii

Write-Host "--- Creating Cthulu GCP Node ($VM_NAME) ---" -ForegroundColor Cyan

# 2. Execute GCloud Creation
gcloud compute instances create $VM_NAME `
    --zone=$ZONE `
    --machine-type=$MACHINE_TYPE `
    --provisioning-model=SPOT `
    --instance-termination-action=STOP `
    --image-family=ubuntu-2204-lts `
    --image-project=ubuntu-os-cloud `
    --boot-disk-size=$DISK_SIZE `
    --boot-disk-type=pd-balanced `
    --tags=cthulu-rdp `
    --enable-nested-virtualization `
    --metadata-from-file startup-script=$STARTUP_FILE

# 3. Create Firewall Rules
Write-Host "--- Configuring Firewall ---" -ForegroundColor Cyan

gcloud compute firewall-rules create allow-cthulu-rdp `
    --allow tcp:8006 `
    --target-tags=cthulu-rdp `
    --description="Allow Cthulu Web RDP access" `
    --quiet

Write-Host "`n--- DEPLOYMENT COMMANDS SENT ---" -ForegroundColor Green
Write-Host "Wait 5-10 minutes for Windows to initialize."
Write-Host "Access yours Windows desktop at: http://<EXTERNAL_IP>:8006"
Write-Host "Use 'gcloud compute instances list' to find your IP."
