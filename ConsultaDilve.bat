@echo off

REM Leer las variables de configuración desde config.txt
for /F "tokens=1,2 delims==" %%A in (config.txt) do (
    set %%A=%%B
)

REM Obtener el ISBN desde el argumento pasado al script y eliminar comillas
set "isbn=%~1"
set "isbn=%isbn:"=%"


REM Agregar una línea de depuración para ver el comando exacto que se está ejecutando
echo Ejecutando la consulta, espere por favor...


REM Ejecutar el script de Python con los parámetros leídos y el ISBN
%PYTHON_PATH_ConsultaDilve% %SCRIPT_PATH_ConsultaDilve% %USER% %PASSWORD% %isbn%
pause
