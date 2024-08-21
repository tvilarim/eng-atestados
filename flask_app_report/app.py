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

# Criação da aplicação Flask
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = '/app/uploads'  # Diretório onde os arquivos serão armazenados
app.config['ALLOWED_EXTENSIONS'] = {'pdf'}  # Extensões permitidas para upload
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'your_default_secret_key')  # Chave secreta da aplicação Flask

# Garantir que o diretório de uploads exista
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Configurações de conexão com o banco de dados
db_config = {
    'host': os.environ.get('MYSQL_HOST', 'mysql-service'),
    'user': os.environ.get('MYSQL_USER', 'root'),
    'password': os.environ.get('MYSQL_PASSWORD', ''),
    'database': os.environ.get('MYSQL_DATABASE', 'atestados')
}

# Função para verificar se o arquivo tem uma extensão permitida
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# Função para processar um arquivo PDF, convertendo-o em imagens e extraindo o texto
def process_pdf(pdf_path):
    images = convert_from_path(pdf_path)  # Converte as páginas do PDF em imagens
    extracted_text = []
    for image in images:
        text = pytesseract.image_to_string(image, output_type=pytesseract.Output.DICT)  # Extrai o texto de cada imagem usando OCR
        extracted_text.append(text['text'])  # Adiciona o texto extraído a uma lista
    combined_text = ' '.join(extracted_text)  # Combina todo o texto extraído em uma única string
    return combined_text

# Função para extrair datas específicas do texto
def extract_dates(text):
    # Normaliza o texto para remover acentos
    normalized_text = unidecode.unidecode(text)

    # Padrões para corresponder "Data de início:" e "Conclusão Efetiva:"
    patterns = [
        r'Data\s*de\s*inicio\s*[:\s]*(\d{2}/\d{2}/\d{4})',  # Ex: "Data de início: 01/01/2023"
        r'Conclusao\s*Efetiva\s*[:\s]*(\d{2}/\d{2}/\d{4})'  # Ex: "Conclusão Efetiva: 31/12/2023"
    ]

    # Compilação dos padrões para maior eficiência
    regex = re.compile('|'.join(patterns), re.IGNORECASE)

    matches = regex.findall(normalized_text)  # Procura por correspondências no texto
    
    start_date, end_date = None, None
    
    # Se encontrar correspondências, tenta analisar as datas
    if matches:
        try:
            if len(matches) > 0:
                start_date = datetime.strptime(matches[0][0], '%d/%m/%Y').strftime('%Y-%m-%d')
            if len(matches) > 1:
                end_date = datetime.strptime(matches[1][0], '%d/%m/%Y').strftime('%Y-%m-%d')
        except ValueError as e:
            print(f"Erro: Formato de data incorreto no texto. Exceção: {e}")
    else:
        # Se os padrões principais não funcionarem, tenta encontrar padrões de data genéricos
        generic_date_pattern = r'\b(\d{2}/\d{2}/\d{4})\b'
        date_matches = re.findall(generic_date_pattern, normalized_text)

        if len(date_matches) >= 2:
            try:
                start_date = datetime.strptime(date_matches[0], '%d/%m/%Y').strftime('%Y-%m-%d')
                end_date = datetime.strptime(date_matches[1], '%d/%m/%Y').strftime('%Y-%m-%d')
            except ValueError as e:
                print(f"Erro: Formato de data incorreto no texto. Exceção: {e}")

    if not start_date and not end_date:
        print("Não foi possível encontrar o padrão de data no texto, salvando sem datas.")
    
    return start_date, end_date

# Função para calcular o hash do texto extraído (usado para evitar duplicações)
def calculate_hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

# Função para extrair palavras com números à direita e salvar no banco de dados
def extract_and_save_words_with_numbers(text, pdf_name):
    try:
        connection = mysql.connector.connect(**db_config)  # Conecta ao banco de dados
        cursor = connection.cursor()

        # Criação da tabela se não existir
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS word_number_pairs (
                id INT AUTO_INCREMENT PRIMARY KEY,
                word VARCHAR(255),
                number VARCHAR(50),
                pdf_name VARCHAR(255)
            )
        ''')

        # Expressão regular para capturar palavras seguidas de números (com ou sem símbolos entre eles)
        pattern = r'\b(\w+)[\s]*[=:\-]?\s*(\d+(\.\d+)?)\b'
        matches = re.findall(pattern, text)

        # Insere os dados extraídos na tabela word_number_pairs
        for match in matches:
            word = match[0]
            number = match[1]
            cursor.execute('''
                INSERT INTO word_number_pairs (word, number, pdf_name) 
                VALUES (%s, %s, %s)
            ''', (word, number, pdf_name))
        
        connection.commit()  # Confirma a transação
    except mysql.connector.Error as err:
        print(f"Erro: {err}")
    finally:
        cursor.close()  # Fecha o cursor
        connection.close()  # Fecha a conexão com o banco de dados

# Função para salvar os dados extraídos no banco de dados MySQL
def save_to_mysql(text, text_hash, start_date, end_date, pdf_name):
    try:
        connection = mysql.connector.connect(**db_config)  # Conecta ao banco de dados
        cursor = connection.cursor()

        # Criação da tabela se não existir
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

        # Verifica se o hash do texto já existe no banco de dados
        cursor.execute('SELECT COUNT(*) FROM pdf_text WHERE text_hash = %s', (text_hash,))
        if cursor.fetchone()[0] > 0:
            return False

        # Insere os dados extraídos na tabela pdf_text
        cursor.execute('''
            INSERT INTO pdf_text (text, text_hash, d1, d2, pdf_name) 
            VALUES (%s, %s, %s, %s, %s)
        ''', (text, text_hash, start_date, end_date, pdf_name))
        
        # Insere o nome do arquivo na tabela uploaded_files
        cursor.execute('''
            INSERT IGNORE INTO uploaded_files (pdf_name) 
            VALUES (%s)
        ''', (pdf_name,))
        
        connection.commit()  # Confirma a transação

        # Extrai e salva as palavras com números associadas
        extract_and_save_words_with_numbers(text, pdf_name)

        return True
    except mysql.connector.Error as err:
        print(f"Erro: {err}")
        return False
    finally:
        cursor.close()  # Fecha o cursor
        connection.close()  # Fecha a conexão com o banco de dados

# Função para buscar relatórios no banco de dados com base em um intervalo de datas
def search_reports(start_date, end_date):
    try:
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor()

        # Consulta para buscar textos de PDF dentro do intervalo de datas especificado
        query = '''
            SELECT text, pdf_name
            FROM pdf_text
            WHERE (d1 <= %s AND d2 >= %s) OR (d1 <= %s AND d2 >= %s)
        '''
        cursor.execute(query, (start_date, end_date, end_date, start_date))
        results = cursor.fetchall()

        cursor.close()
        connection.close()

        # Retorna apenas os nomes dos PDFs e indica que há mais informações disponíveis
        filtered_results = [{'pdf_name': result[1]} for result in results]

        return filtered_results
    except mysql.connector.Error as err:
        print(f"Erro: {err}")
        return []

# Função para buscar os pares de palavras e números do banco de dados
def fetch_word_number_pairs():
    try:
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor()

        # Consulta para buscar todos os pares de palavras e números
        query = '''
            SELECT word, number, pdf_name
            FROM word_number_pairs
        '''
        cursor.execute(query)
        results = cursor.fetchall()

        cursor.close()
        connection.close()

        return results
    except mysql.connector.Error as err:
        print(f"Erro: {err}")
        return []

# Rota principal da aplicação (exibe a página inicial e lida com uploads e buscas)
@app.route('/', methods=['GET', 'POST'])
def index():
    results = []
    selected_start_date = None
    selected_end_date = None
    pdf_list = []
    word_number_pairs = []

    # Obtém a lista de arquivos PDF enviados que estão no banco de dados
    try:
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor()

        cursor.execute('SELECT pdf_name FROM uploaded_files')
        pdf_list = cursor.fetchall()
        pdf_list = [pdf[0] for pdf in pdf_list]

        cursor.close()
        connection.close()
    except mysql.connector.Error as err:
        print(f"Erro: {err}")

    if request.method == 'POST':
        if 'file' in request.files:
            files = request.files.getlist('file')
            if not files:
                flash('Nenhum arquivo selecionado')
                return redirect(request.url)
            
            for file in files:
                if file.filename == '':
                    continue
                
                if file and allowed_file(file.filename):
                    filename = secure_filename(file.filename)  # Garante que o nome do arquivo é seguro
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(file_path)  # Salva o arquivo no diretório de uploads

                    extracted_text = process_pdf(file_path)  # Processa o PDF e extrai o texto
                    text_hash = calculate_hash(extracted_text)  # Calcula o hash do texto

                    start_date, end_date = extract_dates(extracted_text)  # Extrai as datas do texto
                    if not start_date and not end_date:
                        flash(f'Não foi possível extrair datas do PDF: {filename}. Salvando sem datas.', 'warning')
                    else:
                        if save_to_mysql(extracted_text, text_hash, start_date, end_date, filename):
                            flash(f'Arquivo {filename} enviado e processado com sucesso', 'success')
                        else:
                            flash(f'Este arquivo {filename} já está no banco de dados. Pode seguir com o relatório', 'error')
        
        elif 'start_date' in request.form and 'end_date' in request.form:
            selected_start_date_str = request.form.get('start_date')
            selected_end_date_str = request.form.get('end_date')

            if not selected_start_date_str or not selected_end_date_str:
                flash('Por favor, selecione ambas as datas de início e fim.', 'error')
                return redirect(url_for('index'))

            try:
                selected_start_date = datetime.strptime(selected_start_date_str, '%Y-%m-%d')
                selected_end_date = datetime.strptime(selected_end_date_str, '%Y-%m-%d')
            except ValueError:
                flash('Formato de data inválido. Use o calendário para selecionar a data.', 'error')
                return redirect(url_for('index'))

            if selected_end_date < selected_start_date:
                flash('A data final deve ser após a data inicial.', 'error')
                return redirect(url_for('index'))

            results = search_reports(selected_start_date, selected_end_date)  # Busca relatórios dentro do intervalo de datas

            if not results:
                flash('Nenhum relatório encontrado para o intervalo de datas selecionado.', 'info')

    # Busca os pares de palavras e números para exibição
    word_number_pairs = fetch_word_number_pairs()

    return render_template('index.html', 
                           results=results, 
                           selected_start_date=selected_start_date, 
                           selected_end_date=selected_end_date, 
                           pdf_list=pdf_list,
                           word_number_pairs=word_number_pairs)             

# Inicia a aplicação Flask
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
