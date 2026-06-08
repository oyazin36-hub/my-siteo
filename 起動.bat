@echo off
title zumen-pickup

node --version > nul 2>&1
if %errorlevel% neq 0 (
    echo Node.js not found. Please install from https://nodejs.org/
    echo After install, run this file again.
    pause
    exit /b 1
)

if not exist "node_modules" (
    echo Installing packages, please wait...
    npm install
    if %errorlevel% neq 0 (
        echo Install failed.
        pause
        exit /b 1
    )
)

npm start
