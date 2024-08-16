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
import unidecode

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = '/app/uploads'
app.config['ALLOWED_EXTENSIONS'] = {'pdf'}
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'your_default_secret_key')

# Ensure the upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Database connection configuration
db_config = {
    'host': os.environ.get('MYSQL_HOST', 'mysql-service'),
    'user': os.environ.get('MYSQL_USER', 'root'),
    'password': os.environ.get('MYSQL_PASSWORD', ''),
    'database': os.environ.get('MYSQL_DATABASE', 'atestados')
}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def process_pdf(pdf_path):
    images = convert_from_path(pdf_path)
    extracted_text = []
    for image in images:
        text = pytesseract.image_to_string(image, output_type=pytesseract.Output.DICT)
        extracted_text.append(text['text'])
    combined_text = ' '.join(extracted_text)
    return combined_text

import re
from datetime import datetime

def extract_dates(text):
    # Normalize text to remove accents
    normalized_text = unidecode.unidecode(text)

    # Patterns to match "Data de início:" and "Conclusão Efetiva:"
    patterns = [
        r'Data\s*de\s*inicio\s*[:\s]*(\d{2}/\d{2}/\d{4})',  # Matches "Data de início: 01/01/2023"
        r'Conclusao\s*Efetiva\s*[:\s]*(\d{2}/\d{2}/\d{4})'  # Matches "Conclusão Efetiva: 31/12/2023"
    ]

    # Compiling all patterns for efficiency
    regex = re.compile('|'.join(patterns), re.IGNORECASE)

    matches = regex.findall(normalized_text)
    
    start_date, end_date = None, None
    
    # If matches are found, attempt to parse the dates
    if matches:
        try:
            if len(matches) > 0:
                start_date = datetime.strptime(matches[0][0], '%d/%m/%Y').strftime('%Y-%m-%d')
            if len(matches) > 1:
                end_date = datetime.strptime(matches[1][0], '%d/%m/%Y').strftime('%Y-%m-%d')
        except ValueError as e:
            print(f"Error: Date format in the text is incorrect. Exception: {e}")
    else:
        # If the primary pattern doesn't work, try finding any general date patterns in the vicinity
        generic_date_pattern = r'\b(\d{2}/\d{2}/\d{4})\b'
        date_matches = re.findall(generic_date_pattern, normalized_text)

        if len(date_matches) >= 2:
            try:
                start_date = datetime.strptime(date_matches[0], '%d/%m/%Y').strftime('%Y-%m-%d')
                end_date = datetime.strptime(date_matches[1], '%d/%m/%Y').strftime('%Y-%m-%d')
            except ValueError as e:
                print(f"Error: Date format in the text is incorrect. Exception: {e}")

    if not start_date and not end_date:
        print("Could not find the date pattern in the text, saving without dates.")
    
    return start_date, end_date

def calculate_hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

def save_to_mysql(text, text_hash, start_date, end_date, pdf_name):
    try:
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pdf_text (
                id INT AUTO_INCREMENT PRIMARY KEY,
                text LONGTEXT,
                text_hash VARCHAR(64) UNIQUE,
                d1 DATE,
                d2 DATE,
                pdf_name VARCHAR(255)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS uploaded_files (
                id INT AUTO_INCREMENT PRIMARY KEY,
                pdf_name VARCHAR(255) UNIQUE
            )
        ''')

        cursor.execute('SELECT COUNT(*) FROM pdf_text WHERE text_hash = %s', (text_hash,))
        if cursor.fetchone()[0] > 0:
            return False

        cursor.execute('''
            INSERT INTO pdf_text (text, text_hash, d1, d2, pdf_name) 
            VALUES (%s, %s, %s, %s, %s)
        ''', (text, text_hash, start_date, end_date, pdf_name))
        
        cursor.execute('''
            INSERT IGNORE INTO uploaded_files (pdf_name) 
            VALUES (%s)
        ''', (pdf_name,))
        
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
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor()

        query = '''
            SELECT text, pdf_name
            FROM pdf_text
            WHERE (d1 <= %s AND d2 >= %s) OR (d1 <= %s AND d2 >= %s)
        '''
        cursor.execute(query, (start_date, end_date, end_date, start_date))
        results = cursor.fetchall()

        cursor.close()
        connection.close()

        # Return only PDF names and short summaries or indicate more info available
        filtered_results = [{'pdf_name': result[1]} for result in results]

        return filtered_results
    except mysql.connector.Error as err:
        print(f"Error: {err}")
        return []

@app.route('/', methods=['GET', 'POST'])
def index():
    results = []
    selected_start_date = None
    selected_end_date = None
    pdf_list = []

    # Get the list of uploaded PDF files from the database
    try:
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor()

        cursor.execute('SELECT pdf_name FROM uploaded_files')
        pdf_list = cursor.fetchall()
        pdf_list = [pdf[0] for pdf in pdf_list]

        cursor.close()
        connection.close()
    except mysql.connector.Error as err:
        print(f"Error: {err}")

    if request.method == 'POST':
        if 'file' in request.files:
            files = request.files.getlist('file')
            if not files:
                flash('No selected files')
                return redirect(request.url)
            
            for file in files:
                if file.filename == '':
                    continue
                
                if file and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(file_path)

                    extracted_text = process_pdf(file_path)
                    text_hash = calculate_hash(extracted_text)

                    start_date, end_date = extract_dates(extracted_text)
                    if not start_date and not end_date:
                        flash(f'Could not extract dates from the PDF: {filename}. Saved without dates.', 'warning')
                    else:
                        if save_to_mysql(extracted_text, text_hash, start_date, end_date, filename):
                            flash(f'File {filename} successfully uploaded and processed', 'success')
                        else:
                            flash(f'Este arquivo {filename} já está no banco de dados. Pode seguir com o relatório', 'error')
        
        elif 'start_date' in request.form and 'end_date' in request.form:
            selected_start_date_str = request.form.get('start_date')
            selected_end_date_str = request.form.get('end_date')

            if not selected_start_date_str or not selected_end_date_str:
                flash('Please select both start and end dates.', 'error')
                return redirect(url_for('index'))

            try:
                selected_start_date = datetime.strptime(selected_start_date_str, '%Y-%m-%d')
                selected_end_date = datetime.strptime(selected_end_date_str, '%Y-%m-%d')
            except ValueError:
                flash('Invalid date format. Please use the calendar to select a date.', 'error')
                return redirect(url_for('index'))

            if selected_end_date < selected_start_date:
                flash('The end date must be after the start date.', 'error')
                return redirect(url_for('index'))

            results = search_reports(selected_start_date, selected_end_date)

            if not results:
                flash('No reports found for the selected date range.', 'info')

    return render_template('index.html', results=results, selected_start_date=selected_start_date, selected_end_date=selected_end_date, pdf_list=pdf_list)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
