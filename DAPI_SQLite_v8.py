import requests
import xml.etree.ElementTree as ET
import sqlite3
import logging
import sys
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from queue import Queue
from threading import Thread
import os

# Verificación de credenciales
if len(sys.argv) != 3:
    print("\nDebe proporcionar usuario y contraseña como argumentos:")
    print("python DAPI_SQLite_v7.py <usuario> <contraseña>\n")
    sys.exit(1)

user = sys.argv[1]
password = sys.argv[2]

# Crear la carpeta de logs si no existe
log_dir = 'logs'
os.makedirs(log_dir, exist_ok=True)

# Configuración del registro inicial
log_sequence = 1
log_filename = os.path.join(log_dir, f'logs_dapi_sqlite_{log_sequence}.txt')
logging.basicConfig(filename=log_filename, level=logging.INFO, 
                    format='%(asctime)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

# Función para rotar el archivo de registro
def rotate_log_file():
    global log_sequence, log_filename
    log_sequence += 1
    log_filename = os.path.join(log_dir, f'logs_dapi_sqlite_{log_sequence}.txt')
    logging.getLogger().handlers[0].stream.close()
    logging.getLogger().handlers = []
    logging.basicConfig(filename=log_filename, level=logging.INFO, 
                        format='%(asctime)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

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
                if child.tag.split('}')[1] in ['Measure', 'Contributor', 'TitleDetail', 'TextContent', 'PublishingDate', 'Language', 'Subject', 'SupportingResource', 'Audience', 'AudienceRange', 'Publisher', 'Extent', 'SupplyDetail', 'RelatedProduct']:
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

# Función para actualizar registros existentes
def update_existing_record(cursor, table_name, isbn, element):
    columns = {f"{child.tag.split('}')[1] if '}' in child.tag else child.tag}": child.text.strip() for child in element if child.text is not None}

    if not columns:
        return None

    for column, value in columns.items():
        cursor.execute(f'''
            UPDATE OR IGNORE {table_name}
            SET {column} = ?
            WHERE isbn = ?
        ''', (value, isbn))

# Función para procesar un ISBN
def process_isbn(isbn, queue, user, password):
    logging.info(f"Procesando ISBN: {isbn}")
    url_book_info = f"https://www.dilve.es/dilve/dilve/getRecordsX.do?user={user}&password={password}&identifier={isbn}&metadataformat=ONIX&version=3.0"
    
    for attempt in range(3):
        try:
            response = requests.get(url_book_info)
            response.raise_for_status()
            try:
                result = parse_book_info(response.content, isbn)
                if result is None:
                    error = f"Error en el contenido XML para ISBN {isbn}"
                else:
                    queue.put((isbn, result, None))
                    return
            except ET.ParseError as e:
                error = f"Error parseando el XML para ISBN {isbn}: {e}"
        except requests.RequestException as e:
            error = f"Error en la llamada a DILVE para ISBN {isbn}: {e}"

        logging.warning(f"{error}. Intento {attempt + 1} de 3.")
    
    queue.put((isbn, None, error))

# Función para actualizar la base de datos
def db_updater(queue):
    conn = sqlite3.connect('book_all_fields.db')
    cursor = conn.cursor()
    line_count = 0

    while True:
        isbn, result, error = queue.get()
        if isbn is None:
            break
        if error is None:
            for table_name, isbn, element in result:
                if table_name == 'libros':
                    if cursor.execute('SELECT 1 FROM isbns_libros WHERE isbn = ? AND modificado = 1', (isbn,)).fetchone():
                        update_existing_record(cursor, table_name, isbn, element)
                    else:
                        insert_into_table(cursor, table_name, isbn, element)
                else:
                    if cursor.execute('SELECT 1 FROM isbns_libros WHERE isbn = ? AND modificado = 1', (isbn,)).fetchone():
                        cursor.execute(f'DELETE FROM {table_name} WHERE isbn = ?', (isbn,))
                    insert_nested_table(cursor, table_name, isbn, element)
            cursor.execute('''
                UPDATE isbns_libros 
                SET procesado = 1, fecha_procesado = ?, modificado = 0
                WHERE isbn = ?
            ''', (datetime.now().strftime('%Y-%m-%d%H:%M:%S'), isbn))
            logging.info(f"ISBN {isbn} procesado correctamente.")
        else:
            cursor.execute('''
                UPDATE isbns_libros 
                SET procesado = 0, fecha_procesado = ? 
                WHERE isbn = ?
            ''', (datetime.now().strftime('%Y-%m-%d%H:%M:%S'), isbn))
            logging.error(f"Error procesando ISBN {isbn}: {error}")
        conn.commit()
        
        line_count += 1
        if line_count >= 100000:
            rotate_log_file()
            line_count = 0
    
    conn.close()

# Función para procesar los ISBNs en lotes
def process_batch(isbns, queue, user, password):
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(process_isbn, isbn, queue, user, password) for isbn in isbns]
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                logging.error(f"Error procesando un futuro: {e}")

def process_isbn_batches(user, password):
    conn_main = sqlite3.connect('book_all_fields.db')
    cursor_main = conn_main.cursor()

    while True:
        logging.info("Consultando ISBNS no procesados.")
        cursor_main.execute('''
            SELECT isbn 
            FROM isbns_libros 
            WHERE procesado IS NULL 
            ORDER BY id 
            LIMIT 20000
        ''')
        isbns = [row[0] for row in cursor_main.fetchall()]
        
        if not isbns:
            logging.info("No se encontraron ISBNS no procesados. Finalizando.")
            conn_main.close()
            break

        isbns = [isbn for isbn in isbns if isbn is not None]  # eliminar valores None si existen

        if not isbns:
            logging.info("No se encontraron ISBNS válidos para procesar. Finalizando.")
            conn_main.close()
            break

        # Procesar en lotes de 50 ISBNS
        for i in range(0, len(isbns), 50):
            batch = isbns[i:i+50]
            logging.info(f"Procesando un lote de {len(batch)} ISBNS.")

            # Crear una cola para la comunicación entre hilos
            queue = Queue()

            # Iniciar el hilo para las actualizaciones en la base de datos
            db_thread = Thread(target=db_updater, args=(queue,))
            db_thread.start()

            # Procesar el lote
            process_batch(batch, queue)
            logging.info(f"Lote de {len(batch)} ISBNS procesado.")

            # Señalizar el final del hilo de actualización de la base de datos
            queue.put((None, None, None))
            db_thread.join()

            # Rotar el archivo de registro si es necesario
            if os.path.getsize(log_filename) >= 100000:
                rotate_log_file()

    # Optimizar la base de datos
    cursor_main.execute('VACUUM')
    conn_main.close()

# Ejecutar el procesamiento de lotes
process_isbn_batches()

logging.info("Procesamiento completado.")
print("Procesamiento completado.")