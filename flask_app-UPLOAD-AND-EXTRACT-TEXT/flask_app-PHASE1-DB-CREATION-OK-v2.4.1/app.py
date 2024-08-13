from flask import Flask, request, render_template, redirect, url_for, flash
from werkzeug.utils import secure_filename
import os
import mysql.connector
from pdf2image import convert_from_path
import pytesseract
from pytesseract import Output

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = '/app/uploads'
app.config['ALLOWED_EXTENSIONS'] = {'pdf'}
app.secret_key = 'your_secret_key'  # Change this to a secure key

# Ensure the upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Database connection configuration
db_config = {
    'host': 'mysql-service',  # Use the MySQL service name
    'user': 'root',
    'password': 'khg45hj48Fmg',
    'database': 'atestados'
}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def process_pdf(pdf_path):
    # Convert PDF to a list of images
    images = convert_from_path(pdf_path)
    
    # Initialize a list to hold the extracted text
    extracted_text = []
    
    # Extract text from each image using Tesseract
    for image in images:
        text = pytesseract.image_to_string(image, output_type=Output.DICT)
        extracted_text.append(text['text'])
    
    return extracted_text

def save_to_mysql(text_list):
    try:
        # Connect to the MySQL database
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor()

        # Create table if not exists
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pdf_text (
                id INT AUTO_INCREMENT PRIMARY KEY,
                text LONGTEXT
            )
        ''')
        
        # Insert extracted text into the table
        for text in text_list:
            cursor.execute('INSERT INTO pdf_text (text) VALUES (%s)', (text,))
        
        connection.commit()
    except mysql.connector.Error as err:
        print(f"Error: {err}")
    finally:
        cursor.close()
        connection.close()

@app.route('/', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file part')
            return redirect(request.url)
        
        file = request.files['file']
        
        if file.filename == '':
            flash('No selected file')
            return redirect(request.url)
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            
            # Process the PDF and save to MySQL
            extracted_text = process_pdf(file_path)
            save_to_mysql(extracted_text)
            
            flash('File successfully uploaded and processed')
            return redirect(url_for('upload_file'))
    
    return render_template('upload.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
