@echo off
echo ============================================================
echo  GestaoPQLatam - Gerando executavel distribuivel
echo ============================================================
echo.

echo [1/3] Instalando dependencias...
pip install -r requirements.txt
if errorlevel 1 (echo ERRO ao instalar dependencias & pause & exit /b 1)

echo.
echo [2/3] Removendo builds anteriores...
if exist build   rmdir /s /q build
if exist dist    rmdir /s /q dist
if exist GestaoPQLatam.spec del /q GestaoPQLatam.spec

echo.
echo [3/3] Gerando executavel...
pyinstaller ^
  --onefile ^
  --windowed ^
  --name GestaoPQLatam ^
  --add-data "templates;templates" ^
  --hidden-import flask ^
  --hidden-import jinja2 ^
  --hidden-import werkzeug ^
  --hidden-import click ^
  app.py

if errorlevel 1 (
  echo.
  echo ERRO na geracao do executavel.
  pause
  exit /b 1
)

echo.
echo ============================================================
echo  Pronto!
echo  Executavel: dist\GestaoPQLatam.exe
echo
echo  Para distribuir: copie apenas o arquivo .exe.
echo  O banco de dados (dados.db) sera criado automaticamente
echo  na mesma pasta onde o .exe for executado.
echo ============================================================
pause
