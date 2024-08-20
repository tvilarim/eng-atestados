# Use the official Python image from the Docker Hub
FROM python:3.9-slim

# Install system dependencies including poppler-utils and tesseract
RUN apt-get update && \
    apt-get install -y poppler-utils tesseract-ocr && \
    rm -rf /var/lib/apt/lists/*

# Set the working directory
WORKDIR /app

# Copy the requirements file and install Python dependencies
COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt

# Copy the rest of the application code
COPY . .

# Expose the port the app runs on
EXPOSE 5000

# Define the command to run the application
CMD ["python", "app.py"]
