@echo off
rem Build the S10 C-block (runtime gains, filter, sampling and noise test inputs) and drop it next to the stages.
cd /d %~dp0
set CORE=..\..\6_RTOS\ctrl_core
set DMC="C:\Program Files\QSPICE\dm\bin\dmc.exe"
%DMC% -mn -WD -o+speed -DSTACK_RECON_IM=1 -DCTRL_RUNTIME_GAINS -I%CORE% shuffler_ctrl_dll2.cpp %CORE%\shuffler_ctrl.c %CORE%\shuffler_supervisor.c %CORE%\shuffler_mppt.c %CORE%\shuffler_recon.c %CORE%\stack.c kernel32.lib
if errorlevel 1 ( echo BUILD FAILED & exit /b 1 )
del /q *.obj *.map 2>nul
copy /y shuffler_ctrl_dll2.dll "..\Claude's outputs\PCB_Baseline\stages\" >nul
echo built shuffler_ctrl_dll2.dll and copied to PCB_Baseline\stages\
