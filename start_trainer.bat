@echo off
cd /d "%~dp0"
set "PY=C:\Users\flaze\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
if not exist "%PY%" set "PY=python"
start "" "%PY%" "%~dp0trainer.py"
