@echo off
setlocal
cd /d "%~dp0"

python -m pip install -r requirements.txt
python -m pip install pyinstaller
python -m PyInstaller --noconfirm DocFlow.spec

echo.
echo Готово. Файл: dist\DocFlow.exe
echo Скопіюйте DocFlow.exe на потрібний комп'ютер. PostgreSQL має бути доступний.
pause
