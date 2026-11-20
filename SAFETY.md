# Safety and disclaimer

**The Boost Brigade Version 0 board is an unverified student research
prototype, not a product.** It has not been certified, type-tested or
independently reviewed against any electrical safety standard. It operates at
hazardous DC voltages and currents, and it has known design faults (listed
below). Anyone who builds, modifies or operates it does so entirely at their
own risk; see the disclaimer and liability sections of the licences in
[`LICENSE.md`](LICENSE.md).

Only people competent in power electronics should build or operate it, with
appropriate supervision, PPE, an isolated and current-limited source, and a
way to remove power quickly.

## Electrical ratings (Version 0)

These are **design** ratings from the hardware stream's component selection.
**The board was never tested anywhere near them** (see the tested envelope
below). Treat them as absolute maximums, not operating points.

| Quantity | Rating | Where it comes from |
|---|---|---|
| String voltage (all three modules in series, any node to string negative) | **120 V DC max** | Extra-low-voltage limit the design was held under. Above 120 V DC, work requires a licensed electrician. |
| Module (input) voltage | **≤ 45.6 V open-circuit per module**, and **≤ 40 V per module** in a three-module string so the string stays under 120 V | Reference module Aiko A540-MCE60Mw (45.6 V Voc). Bulk capacitors across each module node are 80 V parts. |
| Voltage across any half-bridge (two adjacent modules) | **≤ 91.2 V** | MOSFETs are 100 V parts; peak drain voltage measured about 53 V at the tested operating point |
| Module (input) current | **≤ 14.84 A short-circuit per module** | Reference module Isc; MOSFETs are 45 A parts (chosen for ≥ 25 A, 1.7× Isc, to survive wiring faults) |
| Shuffler (inductor winding) current | **10 A continuous**, the firmware supervisor's rating; coupled inductors saturate at **22.5 A per winding** | `SUP_I_RATED` in `6_RTOS/ctrl_core/params.h`; TDK ERUC23-4R1K datasheet |
| Module power | **540 W class per module** (design reference) | Aiko A540-MCE60Mw. The shufflers only process the *difference* in power between modules, not the full module power. |
| Temperature | Firmware trips at **85 °C** (INA239 die or heatsink sensor) | `APP_TEMP_MAX_C` in `6_RTOS/App/app.h`. Inductor temperature was never measured. |

### Tested envelope (what has actually been demonstrated)

- Three 80 W KickAss KAUSSP80 panels (25.07 V Voc, 4.35 A Isc each), string
  open-circuit about **75 V**.
- String power limited to **≤ 200 W** by the Rigol DL3021 electronic load.
- Switching at 200, 300 and 400 kHz, firmware fw-0.4.1.
- Bench emulation at **≤ 25 V and ≤ 1.3 A per channel** (see the PSU warning
  below).

Anything beyond this envelope is untested.

### Firmware protection limits are set for the 80 W test panels

The boot defaults are a **30 V** per-module over-voltage trip, a **3 V**
under-voltage trip, an **85 V** string over-voltage trip and **85 °C**. They
live in `6_RTOS/App/app.h` and the run-time values in `params_rt`. **If you use
different panels, review and change every one of these limits before
connecting power.**

## Known hazards and design faults

- **No hardware protection on the gate drive.** The 1ED3140 drivers have no
  fault pins and add no dead time. Dead time (200 ns) and over-current trips
  exist **only in firmware** on the Nucleo. A firmware bug, a crashed or
  unflashed Nucleo, a wrong `.ioc` change or a bad duty command can cause
  shoot-through. Never power the converter stage with an unverified firmware
  image.
- **ISO7762 for the string-potential sensor (U10) is wired backwards.** Rework
  is required before closed-loop operation of converter 1.
- **Nucleo ground pads have no net.** A bodge wire is required.
- **The two shufflers cannot be separated under load**, and boards cannot be
  stacked.
- **The coupled-inductor winding arrangement matters.** The control model only
  matches the final arrangement. After any inductor change, check with an
  open-loop probe before closing the loop.
- **The 100 nF HF decoupling (C61–C84) and 470 pF snubber positions must be
  250 V parts**, not the 50 V parts in the original order.
- **Stored energy.** The bulk capacitors (130 µF per node) and the panel or
  supply output capacitance stay charged after the source is removed. Measure
  before touching.
- **Solar panels cannot be switched off.** Any illuminated panel is live.
  Cover the panels before connecting or disconnecting, and never break a DC
  connection under load (XT60s will arc).
- **Reverse polarity, shorts and mis-wiring all happened during testing.** The
  board survived because of its margin, but there is no polarity protection.

## Bench power supplies and electronic loads

**Do not power the board from bench power supplies unless you understand the
interaction below.** We did run a bench test this way (three R&S NGE103
channels in series emulating the three modules, into a Rigol DL3021 e-load),
but it only worked because the operating point was kept far inside the
instruments' ratings. It is not a recommended set-up.

- **Bench supplies cannot sink current.** A shuffler moves current *between*
  module nodes. If it pushes current *into* a node fed by a supply channel
  (during a transient, a fault, a wrong duty or a wrong gain sign), the
  channel cannot absorb it. Its output voltage rises until its OVP trips, or
  the supply is damaged. Set OVP on every channel, and prefer a real PV
  source, or a source with a sink capability or a parallel bleed load.
- **Know the instrument ratings and stay well inside them:**
  - R&S NGE103: **32 V, 3 A and 33.6 W per channel, 100 W total.** Channels
    are earth-free and can be stacked in series to 96 V, but each channel is
    still limited to 32 V. One channel is much smaller than one module the
    board is rated for.
  - Rigol DL3021: **150 V, 40 A, 200 W.** The solar string exceeded 200 W in
    bright sun. That is why the string was held at a fixed 60–61 V instead of
    being tracked, and it is the load's limit, not the board's.
- **Set every limit before enabling outputs:** the supply current limit and
  OVP on each channel, the e-load's OVP/OCP/OPP, the e-load CV set-point below
  its power rating, and the firmware limits above. Enable the e-load input
  last and disable it first.
- **A supply in current limit and an e-load in constant-voltage mode can fight
  each other** and swing the string voltage. Watch the string voltage when
  stepping set-points.

## Disclaimer

All material in this repository and on the project website is provided "as
is", without warranty of any kind, and the authors accept no liability for any
damage, injury or loss arising from its use, to the maximum extent permitted
by law. See section 6 of CERN-OHL-S-2.0 (hardware), section 5 of CC BY 4.0
(documentation) and the MIT licence (software) in [`LICENSES/`](LICENSES/).
