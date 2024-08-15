import os
import re
from flask import Flask, request, render_template, redirect, url_for, flash
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

def extract_dates(text):
    # Regex patterns to extract dates
    start_date_pattern = r'Data de início:\s*(\d{2}/\d{2}/\d{4})'
    end_date_pattern = r'Conclusão Efetiva:\s*(\d{2}/\d{2}/\d{4})'

    # Find the dates in the text
    start_date_match = re.search(start_date_pattern, text)
    end_date_match = re.search(end_date_pattern, text)

    # Convert the dates to dd/mm/yyyy format if found
    start_date = None
    end_date = None

    if start_date_match:
        start_date = datetime.strptime(start_date_match.group(1), '%d/%m/%Y').strftime('%Y-%m-%d')
    if end_date_match:
        end_date = datetime.strptime(end_date_match.group(1), '%d/%m/%Y').strftime('%Y-%m-%d')

    # Check if both dates are found
    if not start_date or not end_date:
        flash("Error: Could not find the required dates in the text.", "error")
    
    return start_date, end_date

def calculate_hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

def save_to_mysql(text, text_hash, start_date, end_date):
    try:
        # Connect to the MySQL database
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor()

        # Create table if not exists
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pdf_text (
                id INT AUTO_INCREMENT PRIMARY KEY,
                text LONGTEXT,
                text_hash VARCHAR(64) UNIQUE,
                d1 DATE,
                d2 DATE
            )
        ''')
        
        # Check if the hash already exists
        cursor.execute('SELECT COUNT(*) FROM pdf_text WHERE text_hash = %s', (text_hash,))
        if cursor.fetchone()[0] > 0:
            return False  # Hash already exists, do not insert

        # Insert extracted text, hash, and dates into the table
        cursor.execute('''
            INSERT INTO pdf_text (text, text_hash, d1, d2) 
            VALUES (%s, %s, %s, %s)
        ''', (text, text_hash, start_date, end_date))
        
        connection.commit()
        return True
    except mysql.connector.Error as err:
        print(f"Error: {err}")
        return False
    finally:
        cursor.close()
        connection.close()

def search_reports(selected_date):
    try:
        # Connect to the MySQL database
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor()

        # Prepare the query to search for matches within the date range
        query = '''
            SELECT text
            FROM pdf_text
            WHERE d1 <= %s AND d2 >= %s
        '''
        cursor.execute(query, (selected_date, selected_date))

        results = cursor.fetchall()

        # Close the connection
        cursor.close()
        connection.close()

        # Extract the text from the results
        filtered_results = [result[0] for result in results]

        return filtered_results
    except mysql.connector.Error as err:
        print(f"Error: {err}")
        return []

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
            
            # Extract dates from the PDF text
            start_date, end_date = extract_dates(extracted_text)
            
            # Check if the dates were successfully extracted
            if not start_date or not end_date:
                flash('Could not extract required dates from the PDF.', 'error')
                return redirect(request.url)
            
            # Check if the content already exists in the database
            if save_to_mysql(extracted_text, text_hash, start_date, end_date):
                flash('File successfully uploaded and processed', 'success')
            else:
                flash('Este arquivo já está no banco de dados. Pode seguir com o relatório', 'error')
            
            return redirect(url_for('upload_file'))
    
    return render_template('upload.html')

@app.route('/search', methods=['GET', 'POST'])
def search():
    if request.method == 'POST':
        selected_date_str = request.form.get('selected_date')
        
        if not selected_date_str:
            flash('Please select a date.', 'error')
            return redirect(url_for('search'))

        try:
            # Convert the date from 'yyyy-mm-dd' to a datetime object
            selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d')
        except ValueError:
            flash('Invalid date format. Please use the calendar to select a date.', 'error')
            return redirect(url_for('search'))

        # Extract dates from the PDF text
        pdf_text = process_pdf('path/to/your/pdf')  # You need to provide the correct path to the PDF
        start_date, end_date = extract_dates(pdf_text)

        # If the dates are missing, the error flash message will already be shown
        if not start_date or not end_date:
            return redirect(url_for('search'))

        # Pass the datetime object to search_reports
        results = search_reports(selected_date)
        return render_template('search.html', results=results, selected_date=selected_date)
    
    return render_template('search.html')

def search_reports(selected_date):
    try:
        # Connect to the MySQL database
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor()
        
        # Prepare the query to search for matches
        query = '''
            SELECT text
            FROM pdf_text
            WHERE text LIKE %s OR text LIKE %s
        '''
        # Create patterns for search
        start_pattern = '%Data de início: %'
        end_pattern = '%Efetiva: %'
        cursor.execute(query, (start_pattern, end_pattern))

        results = cursor.fetchall()

        # Filter results to include only those within the date range
        filtered_results = []
        for result in results:
            text = result[0]
            try:
                # Extract and parse start date
                start_date_str = text.split('Data de início: ')[1].split()[0]
                start_date = datetime.strptime(start_date_str, '%d/%m/%Y')
                
                # Extract and parse end date
                end_date_str = text.split('Efetiva: ')[1].split()[0]
                end_date = datetime.strptime(end_date_str, '%d/%m/%Y')

                # Check if selected_date is between start_date and end_date
                if start_date <= selected_date <= end_date:
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
