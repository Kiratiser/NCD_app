@echo off
title Cafe App Server

echo Changing to project directory...
E:
cd E:\py\NCDNEXT

echo Starting Flask Server...
echo You can access the app at http://127.0.0.1:5000
echo Press CTRL+C in this window to stop the server.

python NCDNEXT_SQLIFE.py

echo Server stopped.
pause