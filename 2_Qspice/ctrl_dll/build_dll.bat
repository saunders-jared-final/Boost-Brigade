@echo off
rem Build the QSPICE C-block from the shared control core and drop it next to the S9 stage.
cd /d %~dp0
set CORE=..\..\6_RTOS\ctrl_core
set DMC="C:\Program Files\QSPICE\dm\bin\dmc.exe"
%DMC% -mn -WD -o+speed -I%CORE% shuffler_ctrl_dll.cpp %CORE%\shuffler_ctrl.c %CORE%\shuffler_supervisor.c %CORE%\shuffler_mppt.c %CORE%\shuffler_recon.c %CORE%\stack.c kernel32.lib
if errorlevel 1 ( echo BUILD FAILED & exit /b 1 )
del /q *.obj *.map 2>nul
copy /y shuffler_ctrl_dll.dll "..\Claude's outputs\PCB_Baseline\stages\" >nul
echo built shuffler_ctrl_dll.dll and copied to PCB_Baseline\stages\
