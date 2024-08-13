#!/bin/bash

# Variables
NAMESPACE="default"  # Kubernetes namespace
DEPLOYMENT_NAME="flask-app-deployment"  # Name of the Kubernetes deployment
CONTAINER_NAME="flask-app"  # Name of the container in the deployment
IMAGE_NAME="tvilarim/flask-app-image"  # Docker image name
TAG="latest"  # Image tag
DOCKERFILE_PATH="."  # Path to your Dockerfile (current directory by default)
DEPLOYMENT_YAML="flask-app-deployment.yaml"  # Path to the deployment YAML file
SERVICE_YAML="flask-app-service.yaml"  # Path to the service YAML file

# Step 1: Check if the image tag exists and apply tagging if necessary
echo "Checking if the Docker image tag ${IMAGE_NAME}:${TAG} exists..."
docker images | grep "${IMAGE_NAME} ${TAG}" > /dev/null 2>&1
if [ $? -ne 0 ]; then
  echo "Tag ${IMAGE_NAME}:${TAG} does not exist. Tagging the image..."
  docker tag flask-app-image:latest ${IMAGE_NAME}:${TAG}
  if [ $? -ne 0 ]; then
    echo "Failed to tag the Docker image."
    exit 1
  fi
else
  echo "Tag ${IMAGE_NAME}:${TAG} already exists."
fi

# Step 2: Build the Docker image
echo "Building the Docker image..."
docker build -t ${IMAGE_NAME}:${TAG} ${DOCKERFILE_PATH}
if [ $? -ne 0 ]; then
  echo "Failed to build the Docker image."
  exit 1
fi

# Step 3: Push the Docker image to the registry
echo "Pushing the Docker image to the registry..."
docker push ${IMAGE_NAME}:${TAG}
if [ $? -ne 0 ]; then
  echo "Failed to push the Docker image."
  exit 1
fi

# Step 4: Check if the deployment exists
echo "Checking if the deployment ${DEPLOYMENT_NAME} exists..."
kubectl get deployment ${DEPLOYMENT_NAME} -n ${NAMESPACE} > /dev/null 2>&1
if [ $? -ne 0 ]; then
  echo "Deployment ${DEPLOYMENT_NAME} does not exist. Applying the deployment YAML file..."
  kubectl apply -f ${DEPLOYMENT_YAML}
  if [ $? -ne 0 ]; then
    echo "Failed to apply the deployment YAML file."
    exit 1
  fi
else
  # Step 5: Update the Kubernetes deployment with the new image
  echo "Updating the Kubernetes deployment..."
  kubectl set image deployment/${DEPLOYMENT_NAME} ${CONTAINER_NAME}=${IMAGE_NAME}:${TAG} -n ${NAMESPACE}
  if [ $? -ne 0 ]; then
    echo "Failed to update the Kubernetes deployment."
    exit 1
  fi

  # Step 6: Monitor the rollout status
  echo "Monitoring the rollout status..."
  kubectl rollout status deployment/${DEPLOYMENT_NAME} -n ${NAMESPACE}
  if [ $? -ne 0 ]; then
    echo "The rollout encountered an issue."
    exit 1
  fi
fi

# Step 7: Apply the service YAML file
echo "Applying the service YAML file..."
kubectl apply -f ${SERVICE_YAML}
if [ $? -ne 0 ]; then
  echo "Failed to apply the service YAML file."
  exit 1
fi

echo "Deployment and service updates complete!"
