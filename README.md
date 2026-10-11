# solar-shuffler-kicad

Updated: 11/10/2026
Where we are ...
- A printed circuit board has been ordered, assembled and power tested using power supplies on a power resistors represent panels and load.
- A control system was designed based off a state space model of the interleaved buck-boost. The latest design is in simulink. This design is based on 4 AIKO solar panels and a battery load (or current sink).
- The sensors on the board are...
    Voltage sensor (possibly could be power meter as well) (ina239)
    Current sensor (TMCS1126B4AQDVGRQ1)
- The main actuators / switch on the board
    Gate Driver (1ED3140MU12F)
    MOSFET (STD45N10F7)
- It has been noted the pcb needs fixing to enable the ina239 that was hidden behind the isolator, however, ignore that for now.
- A qspice model has been tweaked to better reflect the parasitics seen from the pcb.
- An enclosure has been constructed for the pcb to house it and and a few extra components. Including a raspberry pi 4b for data logging, connection to the internet and handling some bonus features. The bonus features include and ir receiver for powering on / off the system, swapping through the preet states / behaviours (ie. open loop mode, closed loop mode, open single shuffler, closed single shuffler posisbly cycling through preset gains). The rgb led and lcd display are there to indicate what state the system is in or if it is erroring out / safe to touch. The temperature sensor is taped to the bottom of the heatsink.

Core Objectives (Where we want to go)...
1. (Could skip to step 2 if redundant). Tweak the simulink model to better reflect the experiment. Possibly add Gauss noise, comb filtering and/or kalman filtering.
2. Integrate the control system with the power electronics system in qpsice. Apply the algorithms from the simulink to the qspice, approximate the signals (ina239 spi, gate driver pwm, hall effect sensor adc). 
3. Create an InfluxDB database and Grafana Dashboard to log and visualise signals from the raspberry pi and nucleo. Note the raspberry pi is connected to a nucleo via uart over the usb port. In the end I would like all the data streams / states / flags I can but the easiest one for initial setup would be the temperature sensor.
4. Construct a FreeRTOS embedded safety-critical program to run on the nucleo. I am imagining a state machine / scheduler. Divide up everything into tasks with priorities. There will need to be some though around the initialisaion / power up mode and power down to do this in a safe way. Like soft switch starts for if we want to push the system. I am thinking tasks like send read voltage, read current, send telemetry, drive gate , estop, current over protection. There is some basic 50% open loop code here to be built upon or referenced.
5. Run the experiment in real life and fix as we go.
6. Write a report and perform a presentation. Once we get results or the board explodes. 

Possibly a bit of house keeping is order. Ideally I would see the following top level folder structure ...
- 0_Documentation
- 1_Datasheets
- 2_Qspice
- 3_Analytical
- 4_Simulink
- 5_Kicad
- 6_RTOS

---------------------------------------------

Solar Panel Reference...
https://www.google.com/search?q=150W+Hard+Frame+Solar+Panel+datasheet&oq=150W+Hard+Frame+Solar+Panel+datasheet&gs_lcrp=EgRlZGdlKgYIABBFGDkyBggAEEUYOdIBCDMxNjdqMGo3qAIBsAIB&sourceid=chrome&source=chrome.ob&ie=UTF-8


Electrical Specifications (22V Model)

• Rated Maximum Power (Pm): 150W
• Power Tolerance: ±3%
• Voltage at Pmax (Vmp): 18.28V
• Current at Pmax (Imp): 8.207A
• Open-Circuit Voltage (Voc): 22.407V
• Short-Circuit Current (Isc): 8.721A
• Normal Operating Cell Temp (NOCT): 45 ± 2°C
• Maximum System Voltage: 1000VDC
• Maximum Series Fuse Rating: 15A
• Operating Temperature: -40°C to +85°C

Mechanical Specifications

• Dimensions: 1160 x 670 x 30 mm
• Weight: 9.32 kg
• Frame: Anodized aluminium alloy
• Protection Rating: IP67 waterproof