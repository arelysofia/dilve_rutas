# Manual de Usuario para SQLite y FileMaker

Este manual proporciona instrucciones para utilizar los scripts de extracción de información desde la API de DILVE y visualizarlos con DB Browser for SQLite.

## Requisitos Previos

- Python 3.x instalado.
- DB Browser for SQLite para visualizar la base de datos.
- FileMaker instalado para gestionar la base de datos `DILVE.fmp12`.
- En el archivo `config.txt` van especificadas las rutas y credenciales para la ejecución de los scripts. Es necesario revisarla por si el ejecutable Python 'python.exe' no se encontrase en la ruta que viene ahí y debe añadir sus propias credenciales de usuario para poder realizar las llamadas HTTP.
- Para poder visualizar correctamente los datos em FileMaker, es necesario tener instalada la fuente `brittanic bold`

## Uso de los Scripts
### Extracción Inicial de ISBNs

1. Debes crear previamente un programa desde la pagina web de dilve, ajustándolo con tus necesidades de extraccion
   (Es recomendable que sea durante periodos de tiempo de 6 meses, por ejemplo, para que no exceda el máximo de
   100.000 registros por consulta)
2. Abre una terminal y navega a la carpeta del proyecto.
3. Ejecuta el siguiente comando para extraer los ISBNs iniciales:
    ```sh
    python ListadoISBNsToSQLite.py <usuario> <contraseña> <nombre_programa>
    ```

### Procesamiento de ISBNs

1. Ejecuta el siguiente comando para procesar los ISBNs obtenidos:
    ```sh
    python DAPI_SQLite_v8.py <usuario> <contraseña>
    ```

### Consulta de ISBN en DILVE

1. Ejecuta el siguiente comando para consultar un ISBN específico en DILVE:
    ```sh
    python ConsultaDilve.py <usuario> <contraseña> <isbn>
    ```

### Actualización de Registros

1. Ejecuta el siguiente comando para actualizar los registros:
    ```sh
    python update/update_records.py <usuario> <contraseña>
    ```

## Visualización de Datos

- Abre `book_all_fields.db` en DB Browser for SQLite para explorar y analizar la información almacenada.
- Utiliza FileMaker para gestionar y visualizar la base de datos `DILVE.fmp12`.

## Solución de Problemas

### Errores Comunes

1. **Error de conexión a la API**:
    - Verifica que las credenciales (usuario y contraseña) sean correctas.
    - Asegúrate de tener una conexión a internet estable.

2. **Errores en la base de datos**:
    - Revisa los archivos de log en la carpeta `logs` para obtener más detalles sobre el error.
    - Asegúrate de que los archivos de la base de datos no estén en uso por otra aplicación.

## Contacto

Para cualquier duda o problema puedes contactarme por correo electrónico [sofia@rodriguezvazquez.com].
