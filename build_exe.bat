@echo off
setlocal
cd /d "%~dp0"

python -m pip install -r requirements.txt
python -m pip install pyinstaller
python -m PyInstaller --noconfirm Aktiv_plus.spec

echo.
echo Готово. Файл: dist\Aktiv_plus.exe
echo Скопіюйте Aktiv_plus.exe на потрібний комп'ютер. PostgreSQL має бути доступний.
pause
