@echo off
title StockMaster Pro - Serveur Web Python
echo ========================================================
echo   Lancement de StockMaster Pro (FastAPI + SQLite)
echo ========================================================
echo.
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
pause
