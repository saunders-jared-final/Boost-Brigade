@echo off
cd /d "C:\Users\jazsa\Documents\Boost-Brigade\2_Qspice\Claude's outputs\PCB_Baseline"
C:\Python312\python.exe run_baseline.py S9
echo RB_EXIT=%ERRORLEVEL%
