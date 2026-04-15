# VERA-16 CPU Simulator

A 16-bit, 2-address architecture CPU simulator designed for university-level CPU architecture education. Built in Python using the `customtkinter` library, this project provides a visual representation of register states, flag states, and step-by-step memory changes across CPU micro-operations. 

Inspired by Morris Mano's Basic Computer, this architecture expands on the accumulator design by introducing 8 general-purpose registers (`R0` - `R7`).

## Features
- **Custom 16-bit Assembler**: Parses mnemonic assembly language into raw machine code directly inside the simulator.
- **Micro-Operation execution**: Simulates Fetch, Decode, and Execute cycles accurately.
- **Dynamic Highlights**: Visually tracks and highlights modifications to general registers, I/O registers, special registers, and CPU flags after every step.
- **Instruction Explanations**: Produces human-readable real-time logs defining what each executing machine instruction represents mathematically inside the CPU logic.

## Usage

If you would prefer not to install Python, you can find a pre-compiled Windows executable `.exe` in the [Releases](../../releases) tab!

### Running from Source
To run this application via source code, make sure you have Python installed securely. 

1. Install the layout requirements via pip:
   ```bash
   pip install -r requirements.txt
   ```
2. Launch the python simulator app file:
   ```bash
   python simulator.py
   ```

### Interface Overview
* **Left Panel**: Contains the CPU hardware tracking (Registers, Special Registers, Flags, Flip-Flops).
* **Middle Panel**: Control terminal containing the Code textbox for assembly code input, Step/Run controls, and the human-readable visual Output Log.
* **Right Panel**: Represents Memory allocations mapped visually per line alongside a strict CPU operational reference.
