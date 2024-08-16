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
        text = pytesseract.image_to_string(image, output_type=Output.DICT)
        extracted_text.append(text['text'])
    combined_text = ' '.join(extracted_text)
    return combined_text

def extract_dates(text):
    date_pattern = (
        r'periodo de (\d{2}/\d{2}/\d{4}) a (\d{2}/\d{2}/\d{4})|'  # Original pattern
        r'Data de inicio: (\d{2}/\d{2}/\d{4}) Conclusão Efetiva: (\d{2}/\d{2}/\d{4})'  # Or new pattern
    )

    match = re.search(date_pattern, text)
    start_date, end_date = None, None

    if match:
        # Extract matched groups, if they exist
        groups = match.groups()
        # Handle the case where both patterns could match
        if len(groups) == 4:
            start_date_str, end_date_str = groups[0], groups[1]
        elif len(groups) == 2:
            start_date_str, end_date_str = groups[2], groups[3]
        else:
            flash("Error: Unexpected match format.", "error")
            return start_date, end_date

        try:
            start_date = datetime.strptime(start_date_str, '%d/%m/%Y').strftime('%Y-%m-%d')
            end_date = datetime.strptime(end_date_str, '%d/%m/%Y').strftime('%Y-%m-%d')
        except ValueError:
            flash("Error: Date format in the text is incorrect.", "error")

    if not start_date or not end_date:
        flash("Error: Could not find the required dates in the text.", "error")
    
    return start_date, end_date

def calculate_hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

def save_to_mysql(text, text_hash, start_date, end_date, pdf_name):
    if not start_date or not end_date:
        return False
    
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
        
        cursor.execute('SELECT COUNT(*) FROM pdf_text WHERE text_hash = %s', (text_hash,))
        if cursor.fetchone()[0] > 0:
            return False

        cursor.execute('''
            INSERT INTO pdf_text (text, text_hash, d1, d2, pdf_name) 
            VALUES (%s, %s, %s, %s, %s)
        ''', (text, text_hash, start_date, end_date, pdf_name))
        
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

        filtered_results = [{'text': result[0], 'pdf_name': result[1]} for result in results]

        return filtered_results
    except mysql.connector.Error as err:
        print(f"Error: {err}")
        return []

@app.route('/', methods=['GET', 'POST'])
def index():
    extracted_text = ""
    results = []
    selected_start_date = None
    selected_end_date = None

    if request.method == 'POST':
        if 'file' in request.files:
            file = request.files['file']
            
            if file.filename == '':
                flash('No selected file')
                return redirect(request.url)
            
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)

                extracted_text = process_pdf(file_path)
                text_hash = calculate_hash(extracted_text)

                start_date, end_date = extract_dates(extracted_text)
                if not start_date or not end_date:
                    flash('Could not extract required dates from the PDF.', 'error')
                else:
                    if save_to_mysql(extracted_text, text_hash, start_date, end_date, filename):
                        flash('File successfully uploaded and processed', 'success')
                    else:
                        flash('Este arquivo já está no banco de dados. Pode seguir com o relatório', 'error')

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

            results = search_reports(selected_start_date, selected_end_date)

    return render_template('index.html', text=extracted_text, results=results, selected_start_date=selected_start_date, selected_end_date=selected_end_date)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
