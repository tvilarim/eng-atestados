#!/bin/bash

# Define the Kubernetes manifest files
CONFIGMAP_FILE="mysql-init-configmap.yaml"
DEPLOYMENT_FILE="my-mysql-deployment.yaml"
SERVICE_FILE="my-mysql-service.yaml"

# Apply the ConfigMap
echo "Applying ConfigMap..."
kubectl apply -f "$CONFIGMAP_FILE"
if [ $? -ne 0 ]; then
    echo "Failed to apply ConfigMap."
    exit 1
fi

# Apply the Deployment
echo "Applying Deployment..."
kubectl apply -f "$DEPLOYMENT_FILE"
if [ $? -ne 0 ]; then
    echo "Failed to apply Deployment."
    exit 1
fi

# Apply the Service
echo "Applying Service..."
kubectl apply -f "$SERVICE_FILE"
if [ $? -ne 0 ]; then
    echo "Failed to apply Service."
    exit 1
fi

echo "Deployment completed successfully."

