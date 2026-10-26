@echo off
chcp 65001 >nul
echo ========================================================
echo   Deutsch im Kontext - Навчальний сервер (FastAPI)
echo   Відкрийте у браузері: http://127.0.0.1:8000
echo ========================================================
start http://127.0.0.1:8000
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 --reload
