@echo off
rem QSPICE only (no QPOST): closed-loop S10 stages are measured by s10_metrics.py from the .qraw
cd /d "C:\Users\jazsa\Documents\Boost-Brigade\2_Qspice\Claude's outputs\PCB_Baseline\stages"
"C:\Program Files\QSPICE\QSPICE64.exe" %1.cir > ..\results\%1.sim.txt 2>&1
echo SIM_EXIT=%ERRORLEVEL%
