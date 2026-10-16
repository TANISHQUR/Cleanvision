@echo off
REM Starts the API on http://127.0.0.1:8000  (run from the project folder)
call .venv\Scripts\activate
uvicorn backend.app.main:app --reload --port 8000 --reload-dir backend
