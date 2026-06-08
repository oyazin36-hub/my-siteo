@echo off
title zumen-pickup

node --version > nul 2>&1
if %errorlevel% neq 0 (
    echo Node.js not found. Please install from https://nodejs.org/
    pause
    exit /b 1
)

if exist "node_modules\electron" (
    echo Removing old electron install...
    rmdir /s /q "node_modules\electron"
)

echo Installing packages, please wait...
npm install

if %errorlevel% neq 0 (
    echo Install failed.
    pause
    exit /b 1
)

npm start
