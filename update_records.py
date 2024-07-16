import requests
import xml.etree.ElementTree as ET
import sqlite3
import logging
import sys
import os
import shutil
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from queue import Queue
from threading import Thread

# Configuración de logging
log_dir = 'logs_isbns'
os.makedirs(log_dir, exist_ok=True)
logging.basicConfig(filename=os.path.join(log_dir, 'log_record_status.txt'), level=logging.INFO,
                    format='%(asctime)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

# Verificar y cerrar estado_proceso.txt si está abierto
try:
    f = open('estado_proceso.txt', 'r+')
    f.close()
except IOError:
    pass

#limpiar el archivo estado_proceso.txt al inicio
with open('estado_proceso.txt', 'w') as f:
    f.write('')

def get_record_status(user, password, from_date):
    url = "https://www.dilve.es/dilve/dilve/getRecordStatusX.do"
    params = {
        "user": user,
        "password": password,
        "fromDate": from_date,
        "type": "A",  # A para todos (nuevos, modificados y borrados)
        "detail": "N"  # N para normal, D para con fecha, S para resumen
    }

    response = requests.get(url, params=params)
    if response.status_code == 200:
        root = ET.fromstring(response.content)
        namespace = {'ns': 'http://www.dilve.es/dilve/api/xsd/getRecordStatusXResponse'}
        
        if root.find('.//ns:error', namespace) is not None:
            logging.error("Error en la llamada: contenido XML contiene <error>")
            return None
        elif root.find('.//ns:existingRecords', namespace) is not None:
            return response.content
        else:
            logging.error("Respuesta no contiene <existingRecords>, posible error en la llamada")
            return None
    else:
        logging.error(f"Error al obtener el estado de los registros: {response.status_code}")
        return None

def procesar_record_status(xml_content):
    root = ET.fromstring(xml_content)
    namespace = {'ns': 'http://www.dilve.es/dilve/api/xsd/getRecordStatusXResponse'}
    
    nuevos = set()
    modificados = set()
    borrados = set()

    for record in root.findall('.//ns:newRecords/ns:record', namespace):
        isbn_element = record.find('ns:id', namespace)
        if isbn_element is not None:
            isbn = isbn_element.text
            nuevos.add(isbn)
        else:
            logging.warning(f"Registro nuevo con elementos faltantes encontrado: {ET.tostring(record, encoding='unicode')}")

    for record in root.findall('.//ns:changedRecords/ns:record', namespace):
        isbn_element = record.find('ns:id', namespace)
        if isbn_element is not None:
            isbn = isbn_element.text
            modificados.add(isbn)
        else:
            logging.warning(f"Registro modificado con elementos faltantes encontrado: {ET.tostring(record, encoding='unicode')}")

    for record in root.findall('.//ns:deletedRecords/ns:record', namespace):
        isbn_element = record.find('ns:id', namespace)
        if isbn_element is not None:
            isbn = isbn_element.text
            borrados.add(isbn)
        else:
            logging.warning(f"Registro eliminado con elementos faltantes encontrado: {ET.tostring(record, encoding='unicode')}")

    return nuevos, modificados, borrados

def crear_nueva_bd():
    if os.path.exists('book_all_fields_update.db'):
        historicos_dir = 'historicos'
        os.makedirs(historicos_dir, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        shutil.move('book_all_fields_update.db', os.path.join(historicos_dir, f'book_all_fields_update_{timestamp}.db'))

    conn = sqlite3.connect('book_all_fields_update.db')
    cursor = conn.cursor()
    
    # SQL para crear la tabla principal
    sql_script = """
    CREATE TABLE IF NOT EXISTS isbns_libros (
        id INTEGER PRIMARY KEY,
        isbn TEXT UNIQUE,
        fecha_extraccion_dilve TEXT,
        es_editorial INTEGER,
        fecha_importacion TEXT,
        nuevo BOOLEAN,
        modificado BOOLEAN,
        procesado BOOLEAN,
        error BOOLEAN,
        eliminado BOOLEAN,
        fecha_procesado TEXT
    );
    """
    
    cursor.executescript(sql_script)
    conn.close()

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

def create_table_if_not_exists(cursor, table_name, columns):
    column_defs = ', '.join([f'{column} TEXT' for column in columns])
    cursor.execute(f'''CREATE TABLE IF NOT EXISTS {table_name} (
                        id INTEGER PRIMARY KEY,
                        isbn TEXT,
                        {column_defs}
                    )''')
    for column in columns:
        try:
            cursor.execute(f'''ALTER TABLE {table_name} ADD COLUMN {column} TEXT''')
        except sqlite3.OperationalError:
            pass

def insert_into_table(cursor, table_name, isbn, element):
    columns = {f"{child.tag.split('}')[1] if '}' in child.tag else child.tag}": child.text.strip() for child in element if child.text is not None}
    
    if not columns:
        return None

    # Crear la tabla si no existe
    create_table_if_not_exists(cursor, table_name, columns.keys())

    column_names = ', '.join(columns.keys())
    placeholders = ', '.join(['?' for _ in columns])

    cursor.execute(f'''INSERT OR IGNORE INTO {table_name} (isbn, {column_names})
                       VALUES (?, {placeholders})''', [isbn] + list(columns.values()))
    return cursor.lastrowid

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

    # Crear la tabla si no existe
    create_table_if_not_exists(cursor, element_tag, nested_data.keys())

    column_names = ', '.join(nested_data.keys())
    placeholders = ', '.join(['?' for _ in nested_data])
    
    nested_data = {k: ' ; '.join(v) for k, v in nested_data.items()}
    cursor.execute(f'''INSERT OR IGNORE INTO {element_tag} (isbn, {column_names})
                       VALUES (?, {placeholders})''', [isbn] + list(nested_data.values()))

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

    # Crear la tabla si no existe
    create_table_if_not_exists(cursor, table_name, nested_data.keys())

    column_names = ', '.join(nested_data.keys())
    placeholders = ', '.join(['?' for _ in nested_data])
    
    nested_data = {k: ' ; '.join(v) for k, v in nested_data.items()}
    cursor.execute(f'''INSERT OR IGNORE INTO {table_name} (isbn, {column_names})
                       VALUES (?, {placeholders})''', [isbn] + list(nested_data.values()))

def update_existing_record(cursor, table_name, isbn, element):
    columns = {f"{child.tag.split('}')[1] if '}' in child.tag else child.tag}": child.text.strip() for child in element if child.text is not None}

    if not columns:
        return None

    # Crear la tabla si no existe
    create_table_if_not_exists(cursor, table_name, columns.keys())

    for column, value in columns.items():
        cursor.execute(f'''
            UPDATE OR IGNORE {table_name}
            SET {column} = ?
            WHERE isbn = ?
        ''', (value, isbn))

def process_isbn(isbn, queue, user, password):
    url_book_info = f"https://www.dilve.es/dilve/dilve/getRecordsX.do?user={user}&password={password}&identifier={isbn}&metadataformat=ONIX&version=3.0"
    
    logging.info(f"Procesando ISBN: {isbn}")
    response = requests.get(url_book_info)
    if response.status_code == 200:
        try:
            result = parse_book_info(response.content, isbn)
            if result is None:  # Manejar el caso donde hay un error en el XML
                queue.put((isbn, None, ValueError("Error en el XML")))
            else:
                queue.put((isbn, result, None))
        except Exception as e:
            logging.error(f"Error procesando ISBN {isbn}: {e}")
            queue.put((isbn, None, e))
    else:
        logging.error(f"No se pudo obtener información para ISBN: {isbn}")
        queue.put((isbn, None, Exception(f"HTTP {response.status_code}")))

def process_batch(isbns, queue, user, password):
    with ThreadPoolExecutor(max_workers=50) as executor:
        future_to_isbn = {executor.submit(process_isbn, isbn, queue, user, password): isbn for isbn in isbns}
        for future in as_completed(future_to_isbn):
            isbn = future_to_isbn[future]
            try:
                future.result()
            except Exception as e:
                logging.error(f"Error procesando ISBN {isbn}: {e}")

def db_updater(queue):
    conn = sqlite3.connect('book_all_fields_update.db')
    cursor = conn.cursor()
    line_count = 0
    
    while True:
        isbn, result, error = queue.get()
        if isbn is None:
            break
        if error is None:
            for table_name, isbn, element in result:
                if table_name == 'libros':
                    insert_into_table(cursor, table_name, isbn, element)
                else:
                    insert_nested_table(cursor, table_name, isbn, element)
            cursor.execute('''
                UPDATE isbns_libros 
                SET procesado = 1, error = 0, fecha_procesado = ? 
                WHERE isbn = ?
            ''', (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), isbn))
            logging.info(f"ISBN {isbn} procesado correctamente.")
        else:
            cursor.execute('''
                UPDATE isbns_libros 
                SET procesado = 0, error = 1, fecha_procesado = ? 
                WHERE isbn = ?
            ''', (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), isbn))
            logging.error(f"Error procesando ISBN {isbn}: {error}")
        conn.commit()
        
        line_count += 1
    
    conn.close()

def process_isbn_batches(user, password):
    conn_main = sqlite3.connect('book_all_fields_update.db')
    cursor_main = conn_main.cursor()

    while True:
        logging.info("Consultando ISBNS no procesados.")
        cursor_main.execute('''
            SELECT isbn 
            FROM isbns_libros 
            WHERE (nuevo = 1 OR modificado = 1) AND procesado IS NOT 1 AND error IS NOT 1
            ORDER BY id 
            LIMIT 20000
        ''')
        isbns = [row[0] for row in cursor_main.fetchall()]
        
        if not isbns:
            logging.info("No se encontraron ISBNS no procesados. Finalizando.")
            break

        isbns = [isbn for isbn in isbns if isbn is not None]  # Eliminar valores None si existen

        if not isbns:
            logging.info("No se encontraron ISBNS válidos para procesar. Finalizando.")
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
            process_batch(batch, queue, user, password)
            logging.info(f"Lote de {len(batch)} ISBNS procesado.")

            # Señalizar el final del hilo de actualización de la base de datos
            queue.put((None, None, None))
            db_thread.join()

    cursor_main.execute('VACUUM')
    conn_main.close()

def actualizar_sqlite(user, password, from_date):
    try:
        xml_content = get_record_status(user, password, from_date)
        if xml_content:
            nuevos, modificados, borrados = procesar_record_status(xml_content)
            
            conn = sqlite3.connect('book_all_fields_update.db')
            cursor = conn.cursor()

            timestamp = datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')

            for isbn in nuevos:
                cursor.execute('''
                    INSERT OR IGNORE INTO isbns_libros (isbn, fecha_extraccion_dilve, es_editorial, fecha_importacion, nuevo, modificado, procesado, error, eliminado)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (isbn, timestamp, 0, timestamp, 1, 0, 0, 0, 0))
                logging.info(f'ISBN {isbn} marcado como nuevo.')

            for isbn in modificados:
                cursor.execute('''
                    INSERT OR IGNORE INTO isbns_libros (isbn, fecha_extraccion_dilve, es_editorial, fecha_importacion, nuevo, modificado, procesado, error, eliminado)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (isbn, timestamp, 0, timestamp, 0, 1, 0, 0, 0))
                logging.info(f'ISBN {isbn} marcado como modificado.')

            for isbn in borrados:
                cursor.execute('''
                    INSERT OR IGNORE INTO isbns_libros (isbn, fecha_extraccion_dilve, es_editorial, fecha_importacion, nuevo, modificado, procesado, error, eliminado)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (isbn, timestamp, 0, timestamp, 0, 0, 0, 0, 1))
                logging.info(f'ISBN {isbn} marcado como eliminado.')

            conn.commit()

            process_isbn_batches(user, password)

            conn.close()
            logging.info("Actualización completada.")

            with open("estado_proceso.txt", "w") as f:
                f.write("Proceso getRecordStatusX completado.")
        else:
            logging.error("No se pudo obtener el contenido XML para actualizar.")
            with open("estado_proceso.txt", "w") as f:
                f.write("No se pudo obtener el contenido XML para actualizar.")
    except Exception as e:
        logging.error(f"Error durante la ejecución: {e}")
        with open("estado_proceso.txt", "w") as f:
            f.write("Error durante la ejecucion.")


def guardar_fecha_extraccion(fecha):
    with open("fromDate.txt", "w") as f:
        f.write(fecha)

def cargar_fecha_extraccion():
    if os.path.exists("fromDate.txt"):
        with open("fromDate.txt", "r") as f:
            return f.read().strip()
    return None

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Uso: python actualizar_registros.py <user> <password>")
        sys.exit(1)

    user = sys.argv[1]
    password = sys.argv[2]

    from_date = cargar_fecha_extraccion()
    if not from_date:
        print("No se pudo cargar la fecha de fromDate.txt")
        sys.exit(1)

    crear_nueva_bd()
    actualizar_sqlite(user, password, from_date)
    guardar_fecha_extraccion(datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ'))

    print("Actualización completada con éxito.")
