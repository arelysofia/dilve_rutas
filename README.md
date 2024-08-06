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

│ └── ... (archivos de log)

├── logs_isbns/

│ └── ... (archivos de log)

├── update/

│ ├── update_records.py

│ ├── update_records.bat

│ ├── book_all_fields_update.db

│ ├── estado_proceso.txt

│ ├── fromDate.txt

│ └── logs_isbns/

│ └── ... (archivos de log)

│ └── historicos/

│ └── ... (Historicos de anteriores actualizaciones book_all_fields_update_(fecha_ult_extraccion).db)



## Descripción de los Archivos

- **config.txt**: Contiene las rutas para los ejecutables.
- **DAPI_SQLite_v8.py**: Procesa los ISBNs y guarda la información en tablas utilizando `getRecordsX` desde la API de DILVE.
- **ListadoISBNsToSQLite.py**: Realiza la extracción inicial de ISBNs con `getRecordListX` desde la API de DILVE.
- **ConsultaDilve.py**: Consulta si un ISBN está en la plataforma de DILVE y, si es así, extrae la información y la deja almacenada en las tablas
- **ConsultaDilve.bat**: Ejecutable de ConsultaDilve.py
- **book_all_fields.db**: Base de datos con los datos de la extracción masiva inicial.
- **DILVE.fmp12**: Base de datos en FileMaker.
- **update/**: Contiene scripts y bases de datos para la actualización de registros.
- **update/update_records.py**: Realiza la llamada `getRecordStatusX`desde la API de DILVE para obtener los registros actualizados e introduce la información recogida en la base de datos book_all_fields_update.db
- **update/update_records.bat**: Ejecutable de update_records.bat
- **update/book_all_fields_update.db**: Base de datos con los datos de la extracción actualizada.
- **update/estado_proceso.txt**: Archivo en el que se indica el estado de la ejecucion de update_record.py, si ha sido o no favorable.
- **update/fromDate.txt**: Contiene la fecha en la que se ejecutó update_records.py con el formato YYYY-MM-DDTHH:MM:SSZ
  
## Resumen Manual de Usuario

### Uso de los Scripts

1. **Extracción inicial de ISBNs**:
    
    ```sh
    python ListadoISBNsToSQLite.py <usuario> <contraseña> <nombre_progrma>
    ```
   

2. **Procesamiento de ISBNs**:
   
    ```sh
    python DAPI_SQLite_v8.py <usuario> <contraseña>
    ```
   

3. **Consulta de ISBN en DILVE**:
 
    ```sh
    python ConsultaDilve.py <usuario> <contraseña> <isbn>
    ```
   


4. **Actualización de registros**: Dentro de la carpeta update\

     ```sh
    python update_records.py <usuario> <contraseña>
    ```


### Visualización de Datos

Abre `book_all_fields.db` en DB Browser for SQLite para explorar y analizar la información almacenada de todos los registros de DILVE.
Abre en `update\book_all_fields_update.db` en DB Browser for SQLite para explorar y analizar la información almacenada de los datos actualizados.
Abre FileMaker y crea un archivo nuevo, desde ahí a través de la importación por ODBC puede incorporse la información de book_all_fields.db book_all_fields_update.db

