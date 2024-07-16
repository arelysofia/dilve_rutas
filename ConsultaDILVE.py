import sqlite3
import requests
import xml.etree.ElementTree as ET
import logging
import sys
import os
from datetime import datetime

# Verificación de credenciales y ISBN
if len(sys.argv) != 4:
    print("\nDebe proporcionar usuario, contraseña e ISBN como argumentos:")
    print("python .\\DAPI_SQLite.py <usuario> <contraseña> <isbn>\n")
    sys.exit(1)
user = sys.argv[1]
password = sys.argv[2]
isbn = sys.argv[3]

# Crear la carpeta de logs si no existe
log_dir = 'logs'
os.makedirs(log_dir, exist_ok=True)

# Configurar el registro inicial
log_filename = os.path.join(log_dir, 'logs_dapi_sqlite.txt')
logging.basicConfig(filename=log_filename, level=logging.INFO, 
                    format='%(asctime)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

# Conectar a la base de datos SQLite
conn = sqlite3.connect('book_all_fields.db')
cursor = conn.cursor()

# Crear tabla isbns_libros si no existe
cursor.execute('''
    CREATE TABLE IF NOT EXISTS isbns_libros (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        isbn TEXT UNIQUE,
        fecha_extraccion_dilve TEXT,
        es_editorial BOOLEAN,
        fecha_importacion TEXT,
        procesado INTEGER,
        fecha_procesado TEXT
    )
''')
cursor.execute('CREATE INDEX IF NOT EXISTS idx_isbn ON isbns_libros (isbn)')
conn.commit()

# Función para parsear las fichas de los libros (xmls)
def parse_book_info(xml_content, isbn):
    root = ET.fromstring(xml_content)
    if root.find('.//{http://www.dilve.es/dilve/api/xsd/getRecordsXResponse}error') is not None:
        return None  # Devolver None si hay un error
    namespace = {'onix': 'http://ns.editeur.org/onix/3.0/reference'}
    product_infos = root.findall('.//onix:Product', namespace)

    result = []
    for product_info in product_infos:
        result.append(('libros', isbn, product_info))
        for child in product_info:
            child_tag = child.tag.split('}')[1] if '}' in child.tag else child.tag
            if len(child) > 0:
                result.append((child_tag, isbn, child))
    return result

# Función para introducir datos en las tablas
def insert_into_table(cursor, table_name, isbn, element):
    columns = {f"{child.tag.split('}')[1] if '}' in child.tag else child.tag}": child.text.strip() for child in element if child.text is not None}
    
    if not columns:
        return None

    column_names = ', '.join(columns.keys())
    placeholders = ', '.join(['?' for _ in columns])
    
    cursor.execute(f'''CREATE TABLE IF NOT EXISTS {table_name} (
                        id INTEGER PRIMARY KEY,
                        isbn TEXT,
                        {column_names}
                    )''')
    for column in columns.keys():
        try:
            cursor.execute(f'''ALTER TABLE {table_name} ADD COLUMN {column} TEXT''')
        except sqlite3.OperationalError:
            pass

    cursor.execute(f'''INSERT OR IGNORE INTO {table_name} (isbn, {column_names})
                       VALUES (?, {placeholders})''', [isbn] + list(columns.values()))
    return cursor.lastrowid

# Función para manejar los elementos específicos y agregar tablas adicionales
def handle_specific_elements(cursor, isbn, element, element_tag):
    nested_data = {}
    
    # Procesar todos los niveles de anidación del XML
    def process_element(element, parent_tag):
        for child in element:
            child_tag = f"{parent_tag}_{child.tag.split('}')[1] if '}' in child.tag else child.tag}".strip('_')
            if len(child) > 0:
                process_element(child, child_tag)
            else:
                if child_tag not in nested_data:
                    nested_data[child_tag] = []
                nested_data[child_tag].append(child.text.strip() if child.text else '')

    process_element(element, element_tag)

    if not nested_data:
        return None

    column_names = ', '.join(nested_data.keys())
    placeholders = ', '.join(['?' for _ in nested_data])
    
    cursor.execute(f'''CREATE TABLE IF NOT EXISTS {element_tag} (
                        id INTEGER PRIMARY KEY,
                        isbn TEXT,
                        {column_names}
                    )''')

    for column in nested_data.keys():
        try:
            cursor.execute(f'''ALTER TABLE {element_tag} ADD COLUMN {column} TEXT''')
        except sqlite3.OperationalError:
            pass

    nested_data = {k: ' ; '.join(v) for k, v in nested_data.items()}
    cursor.execute(f'''INSERT OR IGNORE INTO {element_tag} (isbn, {column_names})
                       VALUES (?, {placeholders})''', [isbn] + list(nested_data.values()))

# Función para poner los datos de los hijos anidados en tablas
def insert_nested_table(cursor, table_name, isbn, element, parent_tag=''):
    nested_data = {}
    
    # Procesar todos los niveles de anidación del XML
    def process_element(element, parent_tag):
        for child in element:
            child_tag = f"{parent_tag}_{child.tag.split('}')[1] if '}' in child.tag else child.tag}".strip('_')
            if len(child) > 0:
                # Verificar si el child_tag es uno de los específicos
                if child.tag.split('}')[1] in ['Measure', 'Contributor', 'TitleDetail', 'TextContent', 'PublishingDate', 'Language', 'Subject', 'SupportingResource', 'Audience', 'AudienceRange','Publisher', 'Extent', 'SupplyDetail','RelatedProduct']:
                    handle_specific_elements(cursor, isbn, child, child.tag.split('}')[1])
                else:
                    process_element(child, child_tag)
            else:
                if child_tag not in nested_data:
                    nested_data[child_tag] = []
                nested_data[child_tag].append(child.text.strip() if child.text else '')

    process_element(element, parent_tag)

    if not nested_data:
        return None

    column_names = ', '.join(nested_data.keys())
    placeholders = ', '.join(['?' for _ in nested_data])
    
    cursor.execute(f'''CREATE TABLE IF NOT EXISTS {table_name} (
                        id INTEGER PRIMARY KEY,
                        isbn TEXT,
                        {column_names}
                    )''')

    for column in nested_data.keys():
        try:
            cursor.execute(f'''ALTER TABLE {table_name} ADD COLUMN {column} TEXT''')
        except sqlite3.OperationalError:
            pass

    nested_data = {k: ' ; '.join(v) for k, v in nested_data.items()}
    cursor.execute(f'''INSERT OR IGNORE INTO {table_name} (isbn, {column_names})
                       VALUES (?, {placeholders})''', [isbn] + list(nested_data.values()))

# Función para procesar un ISBN
def process_isbn(isbn):
    url_book_info = f"https://www.dilve.es/dilve/dilve/getRecordsX.do?user={user}&password={password}&identifier={isbn}&metadataformat=ONIX&version=3.0"
    
    logging.info(f"Procesando ISBN: {isbn}")
    response = requests.get(url_book_info)
    if response.status_code == 200:
        try:
            result = parse_book_info(response.content, isbn)
            if result is None:  # Manejar el caso donde hay un error en el XML
                logging.error(f"Error en el XML para ISBN {isbn}")
                return False
            else:
                # Insertar ISBN en la tabla isbns_libros
                fecha_extraccion_dilve = datetime.now().strftime('%d%m%Y')
                es_editorial = 1
                fecha_importacion = datetime.now().strftime('%d%m%Y')
                procesado = 1
                fecha_procesado = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                cursor.execute('''
                    INSERT OR IGNORE INTO isbns_libros (isbn, fecha_extraccion_dilve, es_editorial, fecha_importacion, procesado, fecha_procesado)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (isbn, fecha_extraccion_dilve, es_editorial, fecha_importacion, procesado, fecha_procesado))
                
                for table_name, isbn, element in result:
                    if table_name == 'libros':
                        insert_into_table(cursor, table_name, isbn, element)
                    else:
                        insert_nested_table(cursor, table_name, isbn, element)
                conn.commit()
                logging.info(f"ISBN {isbn} procesado correctamente.")
                return True
        except Exception as e:
            logging.error(f"Error procesando ISBN {isbn}: {e}")
            return False
    else:
        logging.error(f"No se pudo obtener información para ISBN: {isbn}")
        return False

# Ejecutar el procesamiento del ISBN
if process_isbn(isbn):
    print("Procesamiento completado.")
else:
    print("Error en el procesamiento.")

# Cerrar la conexión
conn.close()
