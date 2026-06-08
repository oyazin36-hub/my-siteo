@echo off
cmd /k "node --version && echo --- npm install start --- && npm install && echo --- DONE --- || echo --- FAILED ---"
