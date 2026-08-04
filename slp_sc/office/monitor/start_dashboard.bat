@echo off
cd /d D:\PythonProjects\support_center\slp_sc\office\monitor
start "" "D:\PythonProjects\.venv\Scripts\python.exe" dashboard_server.py
timeout /t 2
start "" "http://PEERNESHER-SAP3:5052"
