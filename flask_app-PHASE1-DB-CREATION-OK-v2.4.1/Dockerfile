# Use the official Python image from the Docker Hub
FROM python:3.11-slim

# Set the working directory
WORKDIR /app

# Install required system packages including Tesseract
RUN apt-get update && \
    apt-get install -y \
    poppler-utils \
    tesseract-ocr \
    tesseract-ocr-eng

# Copy the application code
COPY app.py /app/

# Copy the templates directory
COPY templates /app/templates/

# Install required Python packages
RUN pip install flask mysql-connector-python pdf2image pytesseract

# Set environment variable for Flask
ENV FLASK_APP=app.py

# Expose the port Flask runs on
EXPOSE 5000

# Run the Flask app
CMD ["flask", "run", "--host=0.0.0.0"]
