#!/bin/bash
set -e

# Configuration
RG="rg-userservice-loadtest"
REGION="centralindia"
VNET_NAME="vnet-loadtest"
SUBNET_NAME="subnet-loadtest"
SERVER_VM_NAME="vm-userservice-server"
LOADGEN_VM_NAME="vm-userservice-loadgen"
SERVER_SIZE="Standard_D4as_v5"
LOADGEN_SIZE="Standard_D2as_v5"

echo "============================================="
echo "Scalable User Service — Azure Deployment Script"
echo "============================================="

# 1. Check Azure CLI installation
if ! command -v az &> /dev/null; then
  echo "Azure CLI (az) is not installed. Installing via Homebrew..."
  brew install azure-cli
fi

# 2. Check Azure CLI authentication
echo "Checking Azure authentication..."
if ! az account show &> /dev/null; then
  echo "Please log in to Azure CLI..."
  az login
fi

# 3. Ensure SSH key pair exists
if [ ! -f ~/.ssh/id_rsa.pub ]; then
  echo "SSH public key not found at ~/.ssh/id_rsa.pub. Generating key pair..."
  ssh-keygen -t rsa -b 4096 -N "" -f ~/.ssh/id_rsa
fi

# 4. Create Resource Group
echo "Creating Resource Group: $RG in region: $REGION..."
az group create --name $RG --location $REGION

# 5. Create Network Security Group (NSG) and Rules
echo "Creating Network Security Group..."
az network nsg create --resource-group $RG --name nsg-loadtest

echo "Adding NSG rule for SSH (port 22)..."
az network nsg rule create --resource-group $RG --nsg-name nsg-loadtest --name Allow-SSH --priority 100 --destination-port-ranges 22 --access Allow --protocol Tcp

echo "Adding NSG rule for Grafana (port 3000)..."
az network nsg rule create --resource-group $RG --nsg-name nsg-loadtest --name Allow-Grafana --priority 110 --destination-port-ranges 3000 --access Allow --protocol Tcp

echo "Adding NSG rule for Locust UI (port 8089)..."
az network nsg rule create --resource-group $RG --nsg-name nsg-loadtest --name Allow-LocustUI --priority 120 --destination-port-ranges 8089 --access Allow --protocol Tcp

# 6. Create VNET and Subnet
echo "Creating VNET ($VNET_NAME) and Subnet ($SUBNET_NAME)..."
az network vnet create \
  --resource-group $RG \
  --name $VNET_NAME \
  --address-prefix 10.0.0.0/16 \
  --subnet-name $SUBNET_NAME \
  --subnet-prefix 10.0.1.0/24 \
  --network-security-group nsg-loadtest

# 7. Create Server VM
echo "Creating Server VM ($SERVER_VM_NAME, $SERVER_SIZE)..."
az vm create \
  --resource-group $RG \
  --name $SERVER_VM_NAME \
  --image Ubuntu2204 \
  --size $SERVER_SIZE \
  --vnet-name $VNET_NAME \
  --subnet $SUBNET_NAME \
  --nsg nsg-loadtest \
  --custom-data infra/cloud-init-server.yml \
  --admin-username ubuntu \
  --ssh-key-values @~/.ssh/id_rsa.pub \
  --public-ip-sku Standard \
  --no-wait

# 8. Create LoadGen VM
echo "Creating LoadGen VM ($LOADGEN_VM_NAME, $LOADGEN_SIZE)..."
az vm create \
  --resource-group $RG \
  --name $LOADGEN_VM_NAME \
  --image Ubuntu2204 \
  --size $LOADGEN_SIZE \
  --vnet-name $VNET_NAME \
  --subnet $SUBNET_NAME \
  --nsg nsg-loadtest \
  --custom-data infra/cloud-init-loadgen.yml \
  --admin-username ubuntu \
  --ssh-key-values @~/.ssh/id_rsa.pub \
  --public-ip-sku Standard

echo "Waiting for VM deployments to complete..."
az vm wait --resource-group $RG --name $SERVER_VM_NAME --created
az vm wait --resource-group $RG --name $LOADGEN_VM_NAME --created

# Get IPs
SERVER_IP=$(az vm show -d -g $RG -n $SERVER_VM_NAME --query publicIps -o tsv)
SERVER_PRIVATE_IP=$(az vm show -d -g $RG -n $SERVER_VM_NAME --query privateIps -o tsv)
LOADGEN_IP=$(az vm show -d -g $RG -n $LOADGEN_VM_NAME --query publicIps -o tsv)

echo "Server Public IP:  $SERVER_IP"
echo "Server Private IP: $SERVER_PRIVATE_IP"
echo "LoadGen Public IP: $LOADGEN_IP"

# 9. Wait for SSH & cloud-init on Server
echo "Waiting for SSH to be ready on Server VM..."
until ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 ubuntu@$SERVER_IP "echo 'SSH is up'" >/dev/null 2>&1; do
  echo -n "."
  sleep 3
done
echo " SSH is up!"

echo "Waiting for Server VM initialization (cloud-init)..."
ssh -o StrictHostKeyChecking=no ubuntu@$SERVER_IP "cloud-init status --wait"

# 10. Wait for SSH & cloud-init on LoadGen
echo "Waiting for SSH to be ready on LoadGen VM..."
until ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 ubuntu@$LOADGEN_IP "echo 'SSH is up'" >/dev/null 2>&1; do
  echo -n "."
  sleep 3
done
echo " SSH is up!"

echo "Waiting for LoadGen VM initialization (cloud-init)..."
ssh -o StrictHostKeyChecking=no ubuntu@$LOADGEN_IP "cloud-init status --wait"

# 11. Sync Credentials between VMs
echo "Downloading load test credentials from Server VM..."
scp -o StrictHostKeyChecking=no ubuntu@$SERVER_IP:/app/.loadtest_users.json ./

echo "Uploading credentials to LoadGen VM..."
scp -o StrictHostKeyChecking=no ./.loadtest_users.json ubuntu@$LOADGEN_IP:/app/
rm ./.loadtest_users.json

# 12. Start Locust on LoadGen pointing to Server's Private IP
echo "Starting Locust on LoadGen VM..."
ssh -o StrictHostKeyChecking=no ubuntu@$LOADGEN_IP "nohup /root/.local/bin/uv run locust -f /app/locustfile.py --host http://$SERVER_PRIVATE_IP:8000 --web-host 0.0.0.0 --web-port 8089 > /app/locust.log 2>&1 < /dev/null &"

echo "============================================="
echo "DEPLOYMENT COMPLETE!"
echo "============================================="
echo "Grafana Dashboard: http://$SERVER_IP:3000 (admin/admin)"
echo "Locust Web UI:     http://$LOADGEN_IP:8089"
echo "---------------------------------------------"
echo "To monitor logs:"
echo "  SSH Server:      ssh ubuntu@$SERVER_IP"
echo "  SSH LoadGen:     ssh ubuntu@$LOADGEN_IP"
echo "============================================="
