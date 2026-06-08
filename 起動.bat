@echo off
echo --- Node.js check --- > log.txt 2>&1
node --version >> log.txt 2>&1

echo --- Removing old electron --- >> log.txt 2>&1
if exist "node_modules\electron" rmdir /s /q "node_modules\electron"

echo --- npm install --- >> log.txt 2>&1
set ELECTRON_MIRROR=https://github.com/electron/electron/releases/download/
npm install >> log.txt 2>&1

echo --- install done --- >> log.txt 2>&1
notepad log.txt

npm start
