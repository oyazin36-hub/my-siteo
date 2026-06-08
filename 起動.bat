@echo off
title zumen-pickup

call :main > log.txt 2>&1
notepad log.txt
exit /b

:main
echo --- Node.js check ---
node --version
if %errorlevel% neq 0 (
    echo [ERROR] Node.js not found. Install from https://nodejs.org/
    exit /b 1
)

echo --- Removing old electron ---
if exist "node_modules\electron" rmdir /s /q "node_modules\electron"

echo --- npm install ---
set ELECTRON_MIRROR=https://github.com/electron/electron/releases/download/
npm install
if %errorlevel% neq 0 (
    echo [ERROR] npm install failed.
    exit /b 1
)

echo --- Starting app ---
npm start
exit /b
