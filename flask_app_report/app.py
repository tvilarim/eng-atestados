import os
import re
from flask import Flask, request, render_template, redirect, url_for, flash
from werkzeug.utils import secure_filename
import mysql.connector
from pdf2image import convert_from_path
import pytesseract
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
        text = pytesseract.image_to_string(image)  # Extrai o texto de cada imagem usando OCR
        extracted_text.append(text)  # Adiciona o texto extraído a uma lista
    combined_text = ' '.join(extracted_text)  # Combina todo o texto extraído em uma única string
    print("Texto extraído do PDF:")  # Adicionando log para verificar o texto extraído
    print(combined_text)
    return combined_text

# Função para extrair e salvar os dados da tabela de serviços
def extract_and_save_service_table(text, pdf_name):
    # Normaliza o texto para capturar variações de "Serviços"
    normalized_text = unidecode.unidecode(text.lower())

    # Expressão regular para localizar a palavra "Serviços" em todas as suas variantes
    service_start_pattern = r'\bservicos?\b'
    service_section_match = re.search(service_start_pattern, normalized_text)

    if service_section_match:
        service_section = normalized_text[service_section_match.end():]

        print("Seção após a palavra 'Serviços':")  # Verificar a seção do texto encontrada
        print(service_section[:1000])  # Mostrando apenas os primeiros 1000 caracteres

        # Expressão regular para capturar linhas de tabela com "Item", "Serviço", "Unidade", "Quantidade"
        table_pattern = r'(\d{2}\s\d{2}\s\d{2})\s+([^\d\s]+(?:\s+[^\d\s]+)*)\s+([A-Za-z]+)\s+([\d,.]+)'
        matches = re.findall(table_pattern, service_section)

        if matches:
            print(f"Matches encontrados: {matches}")  # Debug para verificar os dados extraídos
        else:
            print("Nenhum match foi encontrado na seção 'Serviços'.")
    else:
        print("A palavra 'Serviços' não foi encontrada no texto.")

    # Vamos retornar os matches para exibi-los na interface em vez de salvá-los
    return matches

# Rota principal da aplicação (exibe a página inicial e lida com uploads e buscas)
@app.route('/', methods=['GET', 'POST'])
def index():
    results = []
    selected_start_date = None
    selected_end_date = None
    pdf_list = []
    service_table = []

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

                    # Tentativa de extrair a tabela de serviços
                    service_table = extract_and_save_service_table(extracted_text, filename)
        
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

    return render_template('index.html', 
                           results=results, 
                           selected_start_date=selected_start_date, 
                           selected_end_date=selected_end_date, 
                           pdf_list=pdf_list,
                           service_table=service_table)

# Inicia a aplicação Flask
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
