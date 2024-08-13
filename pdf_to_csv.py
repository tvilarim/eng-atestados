# Import necessary libraries
from pdf2image import convert_from_path
import pytesseract
from pytesseract import Output
import csv

# Specify the path to the Tesseract executable
pytesseract.pytesseract.tesseract_cmd = r'/usr/bin/tesseract'  # Update this path based on your installation

# Step 1: Convert PDF to a list of images
# Replace 'input.pdf' with the path to your PDF file
images = convert_from_path('input.pdf')

# Initialize a list to hold the extracted text
extracted_text = []

# Step 2: Extract text from each image using Tesseract
for image in images:
    # Use Tesseract to do OCR on the image
    text = pytesseract.image_to_string(image, output_type=Output.DICT)
    # Append the extracted text to the list
    extracted_text.append(text)

# Step 3: Save the extracted text to a CSV file
# Replace 'output.csv' with the desired path for your CSV file
with open('output.csv', 'w', newline='', encoding='utf-8') as csv_file:
    csv_writer = csv.writer(csv_file)
    
    # Write each extracted text as a new row in the CSV file
    for text in extracted_text:
        csv_writer.writerow([text])

print("PDF content has been successfully extracted and saved to output.csv")
