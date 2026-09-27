HALF-BRIDGE GATE DRIVER FOR QSPICE (1ED3140 behaviour)
=====================================================

Files
  HalfBridge_Driver.qsch            the driver, fully drawn. A Qspice hierarchical sheet (six port labels).
  HalfBridge_Driver_Testbench.qsch  top sheet: one hierarchical block pointing at the sheet above,
                                    two PWM sources and one half bridge. Runs as is.
  make_driver.py                    writes the two schematics. Values are at the top of the file.
  check/                            readability check: script, report, and the two views it produced.

How Qspice hierarchy works (Help > Schematic Hierarchy)
  * A block whose Symbol Type is empty stands for the schematic of the same name in the same folder.
    Here the block's name text is "HalfBridge_Driver", so it opens HalfBridge_Driver.qsch.
  * The block's pins are ports. They are matched to the sheet's port labels BY NAME, not by order.
  * In the sheet, a port is a net label with "This is a Port" ticked (right click the net).
  * Right click the block > Enter Schematic opens the sheet. Editing the sheet changes every block.
  To make one by hand: right click > Draw Hierarchical Entry, drag a box, right click > Add Port for each
  port, then right click > Enter Schematic and let Qspice create the sheet with the port labels.

How to use it in the converter sheet
  1. Copy HalfBridge_Driver.qsch into the folder of the converter schematic.
  2. Open HalfBridge_Driver_Testbench.qsch, select the yellow block, copy it, paste it once per half bridge.
     Give each copy its own instance name (X1, X2, X3, X4).
  3. Wire PWM_H and PWM_L to the controller's PWM signals (3.3 V logic, referenced to GND).
  4. Wire G_T / S_T to the top FET gate and source, G_B / S_B to the bottom FET gate and source.
     The gate resistors are inside the sheet. Remove the old 4.7 ohm gate resistors and the GDriver block.

What is inside (per FET)
  floating 12 V supply on the FET source
  source stage: Schmitt element, RSRC = 1.5 ohm, output through 10 ohm to the gate   (1ED3140 OUTH + R 10R)
  sink stage:   Schmitt element, RSINK = 1 ohm,  output through 4.7 ohm to the gate  (1ED3140 OUTL + R 4R7)
  both stages: threshold 1.5 V on (IN+ - IN-), hysteresis 0.2 V, delay 70 ns, edges 10 ns
  IN+ = the FET's own PWM, IN- = the other FET's PWM (interlock), EN tied to the supply

Checked
  * QUX netlists the test bench as  X1 ... HalfBridge_Driver  plus  .subckt HalfBridge_Driver
    PWM_H PWM_L G_T S_T G_B S_B  built from the sheet. Two blocks on one sheet share that one definition.
  * Test bench in QSPICE64, 80 V bus, 13 A load, 200 kHz, 200 ns dead time:
      gate swing 0 to 12 V, delay PWM edge to gate 75 to 80 ns,
      dead time at the gates 195 to 198 ns, the two gates never above 1.4 V together.
  * Fault case, PWM_L overlapping PWM_H by 0.9 us: both gates above threshold for 0 ns.
  * Readability check (check/report.txt): no text touches another text, a wire or a symbol.

Not checked
  * The look in the Qspice window itself, and the Enter Schematic command. The check uses Qspice's text
    size measured from a screenshot, but the files have not been opened in the Qspice window by the
    author of this folder.

Assumptions
  * MOSFET model in the test bench: the STD45N10F7 line from "Buck Boost Full Bridge - v3.qsch" with the
    capacitances read as nF / pF (Cgs=1.84n Cgdmin=64.7p Cgdmax=325p) and Cjo=1.2n estimated.
    Replace it with the re-crunched model when that exists.
  * Driver numbers (1.5 / 1 ohm, 70 ns, 10 ns) are datasheet-level estimates for the 1ED3140.
