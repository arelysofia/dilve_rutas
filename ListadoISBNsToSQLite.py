import sqlite3
import xml.etree.ElementTree as ET
import os
import shutil
import re
import requests
from datetime import datetime
import logging
import sys

#verificar de credenciales y parámetros
if len(sys.argv) != 4:
    print("\nDebe proporcionar usuario, contraseña y nombre del programa como argumentos:")
    print("python ListadoISBNsToSQLite.py <usuario> <contraseña> <nombre_programa>\n")
    sys.exit(1)
user = sys.argv[1]
password = sys.argv[2]
program_name = sys.argv[3]

#crear la carpeta de logs si no existe
log_dir = 'E:\\dilve_rutas\\logs_isbns'
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

#configurar el registro en el archivo log.txt
logging.basicConfig(filename='log.txt', level=logging.INFO,
                    format='%(asctime)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

#conectar a la base de datos SQLite
conn = sqlite3.connect('book_all_fields.db')
cursor = conn.cursor()

#crear tabla si no existe y agregar índice
cursor.execute('''
    CREATE TABLE IF NOT EXISTS isbns_libros (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        isbn TEXT UNIQUE,
        fecha_extraccion_dilve TEXT,
        es_editorial BOOLEAN,
        fecha_importacion TEXT
    )
''')
cursor.execute('CREATE INDEX IF NOT EXISTS idx_isbn ON isbns_libros (isbn)')

conn.commit()

#función para procesar el XML
def procesar_xml(filename, program):
    # Parsear el archivo XML
    tree = ET.parse(filename)
    root = tree.getroot()
    namespace = {'ns': 'http://www.dilve.es/dilve/api/xsd/getRecordListXResponse'}

    #extraer los ISBNS y asegurar que son únicos utilizando un conjunto
    isbns = set(record.find('ns:id', namespace).text for record in root.findall('.//ns:record', namespace))

    #extraer la fecha de extracción y el tipo de archivo desde el nombre del programa
    match = re.match(r'getRecordListX_(\w+)_(\w+)_(E|AE)', program)
    if not match:
        logging.error(f"Nombre del programa no coincide con el patrón esperado: {program}")
        return

    program_type = match.group(1)
    extraction_format = match.group(2)
    program_suffix = match.group(3)
    fecha_extraccion_dilve = datetime.now().strftime('%Y%m%d')
    es_editorial = program_suffix == 'E'
    fecha_importacion = datetime.now().strftime('%d%m%Y')

    #insertar cada ISBN en la base de datos, asegurando que no haya duplicados
    cursor.execute('BEGIN TRANSACTION')
    for isbn in isbns:
        cursor.execute('SELECT COUNT(*) FROM isbns_libros WHERE isbn = ?', (isbn,))
        count = cursor.fetchone()[0]
        if count == 0:
            cursor.execute('''
                INSERT INTO isbns_libros (isbn, fecha_extraccion_dilve, es_editorial, fecha_importacion)
                VALUES (?, ?, ?, ?)
            ''', (isbn, fecha_extraccion_dilve, es_editorial, fecha_importacion))
            logging.info(f'ISBN {isbn} insertado.')
        else:
            logging.info(f'ISBN {isbn} omitido (ya existente).')
    conn.commit()

    logging.info(f'{len(isbns)} ISBNS procesados de {filename}.')

    #mover el archivo a la carpeta correspondiente
    output_dir = os.path.join('listado_isbns_procesados_sqlite', program)
    os.makedirs(output_dir, exist_ok=True)
    shutil.move(filename, os.path.join(output_dir, os.path.basename(filename)))

#funnción para obtener el XML desde la API
def fetch_isbns(user, password, program):
    url = f"https://www.dilve.es/dilve/dilve/getRecordListX.do?user={user}&password={password}&type=L&program={program}"
    response = requests.get(url)

    if response.status_code == 200:
        filename = f"{program}.xml"
        with open(filename, 'wb') as file:
            file.write(response.content)
        procesar_xml(filename, program)
    else:
        logging.error(f"Error al obtener el listado de ISBNs: {response.status_code}")

#Obtener los ISBNs y procesar y guardar el XML
fetch_isbns(user, password, program_name)



#cerrar la conexión
conn.close()

logging.info("Procesamiento completado.")
print("Proceso completado.")
