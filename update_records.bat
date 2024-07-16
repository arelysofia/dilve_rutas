@echo off
REM Guardar el directorio actual (donde está el .bat)
set CURRENT_DIR=%~dp0

REM Cambiar al directorio raíz del proyecto (dilve_rutas)
cd /d %CURRENT_DIR%\..

REM Imprimir el directorio actual para depuración
echo Ejecutando el programa, espere por favor...

REM Verificar la existencia de config.txt
if not exist config.txt (
    echo No se encontró config.txt
    pause
    exit /b
)

REM Leer las variables de configuración desde config.txt
for /F "tokens=1,2 delims==" %%A in (config.txt) do (
    set %%A=%%B
)



REM Cambiar al directorio de update para ejecutar el script de Python
cd update


REM Ejecutar el script de Python con las credenciales
"%PYTHON_PATH%" "%cd%\%SCRIPT_PATH%" %USER% %PASSWORD%



REM Comprobar si el script se ejecutó correctamente
if %errorlevel% equ 0 (
    echo El script de Python se ha ejecutado correctamente.
) else (
    echo Hubo un error al ejecutar el script de Python.
)

REM Esperar a que el script termine y mostrar un mensaje
pause
