# Licensing

Boost Brigade is a multi-licensed project. Different parts of the repository
have different authors and different licences. The full licence texts are in
[`LICENSES/`](LICENSES/).

| Part | Folder(s) | Licence | Copyright |
|---|---|---|---|
| **PCB design** (schematic, layout, Gerbers, BOM) | `5_Kicad/` (except `5_Kicad/libs/`) | [CERN-OHL-S-2.0](LICENSES/CERN-OHL-S-2.0.txt) | © 2026 Son Nguyen |
| **Mechanical enclosure** | `9_Mechanical_Enclosure_CAD/` | [CERN-OHL-S-2.0](LICENSES/CERN-OHL-S-2.0.txt) | © 2026 Jared Saunders |
| **Analytical solution, controller structure, models** | `3_Analytical/`, `4_Simulink/`, `2_Qspice/` | [CC BY 4.0](LICENSES/CC-BY-4.0.txt) | © 2026 Jared Saunders |
| **Documentation and results** | `0_Documentation/`, `8_Results/` | [CC BY 4.0](LICENSES/CC-BY-4.0.txt) | © 2026 their respective authors (Son Nguyen for his reports, Jared Saunders for his) |
| **Firmware, Pi software, website code** | `6_RTOS/`, `7_Pi/`, `site/` | [MIT](LICENSES/MIT.txt) | © 2026 Jared Saunders and the Boost Brigade contributors |

Each of these folders has its own `LICENSE.md` notice.

## What this means in practice

- **PCB and enclosure (CERN-OHL-S-2.0, strongly reciprocal):** you may study,
  modify, make and sell the hardware or anything derived from it. If you
  distribute the design files, or sell or give away boards built from them,
  you must (a) credit the original designer, (b) release your complete,
  modified design source under CERN-OHL-S-2.0, and (c) state where that
  source can be found on the product or its documentation. You may not
  present the design as your own work.
- **Analytical work and documentation (CC BY 4.0):** reuse, adapt and build on
  it freely, including commercially, as long as you give appropriate credit
  (see [`CITATION.cff`](CITATION.cff)) and indicate what you changed.
- **Software (MIT):** do what you like with it; keep the copyright and licence
  notice in copies.

## Credit

- **Son Nguyen**: power electronics and PCB design (Version 0 board).
- **Jared Saunders**: derivation of the analytical solution for the power
  shuffler, the controller structure, simulation and test ladder, and the
  mechanical enclosure.

Supervised by Assoc Prof Geoff Walker, Queensland University of Technology
(EGH490 Research Project, 2026).

If you use the analytical results or controller structure in academic or
published work, please cite this repository (GitHub's "Cite this repository"
button reads [`CITATION.cff`](CITATION.cff)).

## Third-party material (not covered by the licences above)

These files belong to their original owners and keep their own terms:

- `1_Datasheets/`: manufacturer datasheets and tools.
- `5_Kicad/libs/`: vendor symbols, footprints and 3D models.
- `6_RTOS/Drivers/`: STMicroelectronics HAL and Arm CMSIS (see the licence
  files inside), and any STM32CubeMX-generated files that carry their own
  licence header.
- `2_Qspice/`: vendor-supplied device and PV models.
- Anything else that carries its own licence or copyright notice.

## No warranty

This is a student research prototype operating at hazardous voltages. All
material is provided "as is", without warranty of any kind; see the
disclaimer sections of each licence. Electrical ratings, known hazards and
bench-equipment warnings are in [`SAFETY.md`](SAFETY.md).
