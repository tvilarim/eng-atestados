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
            WHERE text LIKE %s OR text LIKE %s
        '''
        start_pattern = '%Data de início:%'
        end_pattern = '%Conclusão Efetiva:%'
        cursor.execute(query, (start_pattern, end_pattern))
        
        results = cursor.fetchall()
        
        # Convert start_date and end_date to datetime objects
        start_date = datetime.strptime(start_date, '%d/%m/%Y')
        end_date = datetime.strptime(end_date, '%d/%m/%Y')

        # Filter results to include only those within the date range
        filtered_results = []
        for result in results:
            text = result[0]
            try:
                # Extract and parse the "Data de início" date
                start_date_str = text.split('Data de início: ')[1].split()[0]
                start_date_text = datetime.strptime(start_date_str, '%d/%m/%Y')

                # Extract and parse the "Conclusão Efetiva" date
                end_date_str = text.split('Conclusão Efetiva: ')[1].split()[0]
                end_date_text = datetime.strptime(end_date_str, '%d/%m/%Y')

                # Check if the extracted dates fall within the specified range
                if start_date <= start_date_text <= end_date and start_date <= end_date_text <= end_date:
                    filtered_results.append(text)
            except (IndexError, ValueError):
                # Handle any parsing errors
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

@app.route('/search', methods=['GET', 'POST'])
def search():
    if request.method == 'POST':
        selected_date = request.form.get('selected_date')
        
        if not selected_date:
            flash('Please select a date.', 'error')
            return redirect(url_for('search'))

        try:
            selected_date = datetime.strptime(selected_date, '%Y-%m-%d')
        except ValueError:
            flash('Invalid date format. Please use the calendar to select a date.', 'error')
            return redirect(url_for('search'))

        results = search_reports(selected_date)
        return render_template('search.html', results=results, selected_date=selected_date)
    
    return render_template('search.html')

def search_reports(selected_date):
    try:
        # Connect to the MySQL database
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor()
        
        query = '''
            SELECT text
            FROM pdf_text
            WHERE text LIKE %s OR text LIKE %s
        '''
        start_pattern = '%Data de início:%'
        end_pattern = '%Conclusão Efetiva:%'
        cursor.execute(query, (start_pattern, end_pattern))
        
        results = cursor.fetchall()
        
        # Convert selected_date to datetime object
        selected_date = datetime.strptime(selected_date, '%Y-%m-%d')

        # Filter results to include only those within the date range
        filtered_results = []
        for result in results:
            text = result[0]
            try:
                # Extract and parse the "Data de início" date
                start_date_str = text.split('Data de início: ')[1].split()[0]
                start_date_text = datetime.strptime(start_date_str, '%d/%m/%Y')

                # Extract and parse the "Conclusão Efetiva" date
                end_date_str = text.split('Conclusão Efetiva: ')[1].split()[0]
                end_date_text = datetime.strptime(end_date_str, '%d/%m/%Y')

                # Check if the extracted dates fall within the specified range
                if start_date_text <= selected_date <= end_date_text:
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
