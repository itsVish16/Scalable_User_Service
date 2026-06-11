#!/bin/bash
set -e

RG="rg-userservice-loadtest"

echo "============================================="
echo "Scalable User Service — Azure Cleanup"
echo "============================================="
echo "This will DELETE the resource group: $RG"
echo "and all resources inside it (VMs, network, disks)."
echo "This will stop Azure billing immediately."
echo "============================================="

# If --yes is passed, bypass prompt
if [ "$1" = "--yes" ] || [ "$1" = "-y" ]; then
  CONFIRM="y"
else
  read -p "Are you sure you want to delete all resources? (y/n) " -n 1 -r CONFIRM
  echo
fi

if [[ $CONFIRM =~ ^[Yy]$ ]]
then
  echo "Deleting resource group $RG (this can take a few minutes)..."
  az group delete --name $RG --yes --no-wait
  echo "Cleanup requested. Resource group is being deleted in the background."
  echo "Billing will stop as soon as the VMs are terminated."
else
  echo "Cleanup cancelled."
fi
