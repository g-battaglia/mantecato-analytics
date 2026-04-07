#!/bin/bash
# Stop and remove demo containers
container stop demo-db demo-backend demo-frontend 2>/dev/null
container rm demo-db demo-backend demo-frontend 2>/dev/null
echo "Demo stopped."
