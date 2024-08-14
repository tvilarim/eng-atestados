import os
from flask import Flask, request, render_template, redirect, url_for, flash, jsonify
from werkzeug.utils import secure_filename
import mysql.connector
from pdf2image import convert_from_path
import pytesseract
from pytesseract import Output
import hashlib
from datetime import datetime

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = '/app/uploads'
app.config['ALLOWED_EXTENSIONS'] = {'pdf'}
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'your_default_secret_key')  # Securely get the secret key

# Ensure the upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Database connection configuration using environment variables
db_config = {
    'host': os.environ.get('MYSQL_HOST', 'mysql-service'),
    'user': os.environ.get('MYSQL_USER', 'root'),
    'password': os.environ.get('MYSQL_PASSWORD', ''),
    'database': os.environ.get('MYSQL_DATABASE', 'atestados')
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
    
    # Join the extracted text into a single string
    combined_text = ' '.join(extracted_text)
    
    return combined_text

def calculate_hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

def save_to_mysql(text, text_hash):
    try:
        # Connect to the MySQL database
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor()

        # Create table if not exists
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pdf_text (
                id INT AUTO_INCREMENT PRIMARY KEY,
                text LONGTEXT,
                text_hash VARCHAR(64) UNIQUE
            )
        ''')
        
        # Check if the hash already exists
        cursor.execute('SELECT COUNT(*) FROM pdf_text WHERE text_hash = %s', (text_hash,))
        if cursor.fetchone()[0] > 0:
            return False  # Hash already exists, do not insert

        # Insert extracted text and hash into the table
        cursor.execute('INSERT INTO pdf_text (text, text_hash) VALUES (%s, %s)', (text, text_hash))
        connection.commit()
        
        return True
    except mysql.connector.Error as err:
        print(f"Error: {err}")
        return False
    finally:
        cursor.close()
        connection.close()

def search_reports(start_date, end_date):
    try:
        # Connect to the MySQL database
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor()
        
        # Prepare the query to search for matches
        query = '''
            SELECT text
            FROM pdf_text
            WHERE text LIKE %s
        '''
        search_pattern = f'%Data de início: {start_date}%'
        cursor.execute(query, (search_pattern,))
        
        results = cursor.fetchall()
        
        # Filter results to include only those within the date range
        filtered_results = []
        for result in results:
            text = result[0]
            # Extract date from the text and check if it falls within the range
            # Assuming date format is "dd/mm/yyyy"
            try:
                date_str = text.split('Data de início: ')[1].split()[0]
                date = datetime.strptime(date_str, '%d/%m/%Y')
                if datetime.strptime(start_date, '%d/%m/%Y') <= date <= datetime.strptime(end_date, '%d/%m/%Y'):
                    filtered_results.append(text)
            except (IndexError, ValueError):
                continue
        
        return filtered_results
    except mysql.connector.Error as err:
        print(f"Error: {err}")
        return []
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
            
            # Process the PDF and get the combined text
            extracted_text = process_pdf(file_path)
            text_hash = calculate_hash(extracted_text)
            
            # Check if the content already exists in the database
            if save_to_mysql(extracted_text, text_hash):
                flash('File successfully uploaded and processed', 'success')
            else:
                flash('Este arquivo já está no banco de dados. Pode seguir com o relatório', 'error')
            
            return redirect(url_for('upload_file'))
    
    return render_template('upload.html')

@app.route('/search', methods=['GET'])
def search():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    if not start_date or not end_date:
        flash('Start date and end date are required.', 'error')
        return redirect(url_for('upload_file'))
    
    try:
        datetime.strptime(start_date, '%d/%m/%Y')
        datetime.strptime(end_date, '%d/%m/%Y')
    except ValueError:
        flash('Invalid date format. Use dd/mm/yyyy.', 'error')
        return redirect(url_for('upload_file'))
    
    results = search_reports(start_date, end_date)
    return render_template('upload.html', results=results)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
