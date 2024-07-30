# dilve_rutas

Este proyecto tiene como objetivo crear una aplicación en FileMaker que contenga una réplica de todos los registros en DILVE y se mantenga constantemente actualizada. Para lograr esto de manera práctica, se utiliza una base de datos intermedia SQLite.

## Estructura del Proyecto


dilve_rutas/

├── config.txt

├── DAPI_SQLite_v8.py

├── ListadoISBNsToSQLite.py

├── ConsultaDilve.py

├── ConsultaDilve.bat

├── book_all_fields.db

├── DILVE.fmp12

├── logs/

├── logs_isbns/

│ └── ... (archivos de log)

├── update/

│ ├── update_records.py

│ ├── update_records.bat

│ ├── book_all_fields_update.db

│ ├── estado_proceso.txt

│ ├── fromDate.txt

│ └── logs_isbns/

│ └── historicos/



## Descripción de los Archivos

- **config.txt**: Contiene las rutas para los ejecutables.
- **DAPI_SQLite_v8.py**: Procesa los ISBNs y guarda la información en tablas utilizando `getRecordsX` desde la API de DILVE.
- **ListadoISBNsToSQLite.py**: Realiza la extracción inicial de ISBNs con `getRecordListX` desde la API de DILVE.
- **ConsultaDilve.py**: Consulta si un ISBN está en la plataforma de DILVE y, si es así, extrae la información.
- **book_all_fields.db**: Base de datos con los datos de la extracción masiva inicial.
- **DILVE.fmp12**: Base de datos en FileMaker.
- **update/**: Contiene scripts y bases de datos para la actualización de registros.

## Manual de Usuario

### Requisitos Previos

- Python 3.x instalado.
- DB Browser for SQLite para visualizar la base de datos.

### Uso de los Scripts

1. **Extracción inicial de ISBNs**:
    
    python `ListadoISBNsToSQLite.py`   <usuario> <contraseña> <nombre_programa>
   

2. **Procesamiento de ISBNs**:
   
    python `DAPI_SQLite_v8.py`   <usuario> <contraseña>
   

3. **Consulta de ISBN en DILVE**:
 
    python `ConsultaDilve.py`   `<usuario>` `<contraseña>` `<isbn>`


4. **Actualización de registros**:

    python `update/update_records.py`   `<usuario>` `<contraseña>`


### Visualización de Datos

Abre `book_all_fields.db` en DB Browser for SQLite para explorar y analizar la información almacenada de todos los registros de DILVE.
Abre en `update\ book_all_fields_update.db` en DB Browser for SQLite para explorar y analizar la información almacenada de los datos actualizados.
