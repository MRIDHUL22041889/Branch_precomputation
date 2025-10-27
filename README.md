# Branch Precomputation Unit (BPU)

A lightweight Branch Precomputation Unit (BPU) designed to reduce branch penalties in an in-order RV32I pipeline by pre-decoding upcoming instructions, computing branch targets early, and resolving conditional outcomes using forwarded or register values — all before the normal decode/execute stages complete.

---

## Table of contents

- [Overview](#overview)  
- [Key features](#key-features)  
- [Design & Architecture](#design--architecture)  
  - [Stages](#stages)  
  - [Components](#components)  
- [Classes & high-level behavior](#classes--high-level-behavior)  
- [Pipeline integration](#pipeline-integration)  
- [Instruction memory and labels](#instruction-memory-and-labels)  
- [Directory structure](#directory-structure)  
- [Getting started](#getting-started)  
- [Running the simulator](#running-the-simulator)  
- [License](#license)
- [To Do](#To_do)
---

## Overview

Modern processors suffer pipeline stalls, flushes, and wasted cycles when branch instructions are encountered, especially when branches are data-dependent. Many high-performance dynamic predictors (e.g., TAGE) are unsuitable for low-power or constrained in-order processors. The BPU offers a simpler, lower-power approach: run a small, parallel pre-decode and pre-evaluation window ahead of the main pipeline to reduce branch penalties.

Instead of waiting for ID/EX to evaluate branch conditions, the BPU:
- Pre-decodes and classifies upcoming instructions early.
- Pre-computes Branch Target Addresses (BTAs).
- Uses forwarded or register values to evaluate branch conditions early.
- Redirects the PC immediately when a branch is determined taken, avoiding unnecessary fetches and pipeline bubbles.

This enables simultaneous evaluation of two upcoming instructions, earlier target calculation, and improved fetch efficiency.

---

## Key features

- Early identification of branch/jump instructions (pre-decode).
- Lightweight BTA computation unit (doesn't stall main ALU).
- Early condition evaluation using forwarded data from pipeline registers.
- Support for all RV32I base formats: R, I, S, B, U, J.
- Simple dependency detection to request stalls when necessary (e.g., load-use hazards).
- Configurable two-instruction prefetch window for improved throughput.

---

## Design & Architecture

The BPU is structured around two precomputation stages and a small set of compact components.

### Stages

- Stage 1 — Pre-decode & dependency check (_run_bpu_stage1)
  - Fetch two consecutive instructions (instr1, instr2).
  - Identify branch/jump instructions and compute their BTAs.
  - Check dependencies with ID/EX/MEM pipeline stages (load-use hazards, register dependencies).
  - Request a stall when dependencies prevent safe early resolution.
  - If an unconditional jump (jal) is found, mark it taken immediately with computed BTA.

- Stage 2 — Branch evaluation (_run_bpu_stage2)
  - Resolve branch conditions using:
    - Register file values
    - Forwarded values from ID/EX/MEM/WB
    - Precomputed ALU results
  - If the branch is taken, return the redirect target PC (BTA).
  - Otherwise, execution continues normally.

- run_bpu_cycle()
  - Called each clock cycle to integrate the stages:
    - Run Stage 1 on newly fetched PCs.
    - If dependency-free, run Stage 2 for previously queued branches.
    - Emit a directive to the fetch unit on taken branches to redirect PC immediately.
    - Precompute results for the current ID-stage instruction to support early forwarding.

### Components

1. BTA Commuter (MinimalALU)
   - Lightweight arithmetic unit to pre-compute PC + offset.
   - Example:
     ```python
     class MinimalALU:
         def compute_bta(self, pc, imm_offset):
             return pc + imm_offset
     ```

2. Comparator
   - Evaluates branch conditions (beq, bne, blt, bge, etc.), supporting signed/unsigned where needed.
   - Example:
     ```python
     class Comparator:
         def is_taken(self, op, v1, v2):
             return {
                 "beq": v1 == v2,
                 "bne": v1 != v2,
                 "blt": int(v1) < int(v2),   # signed
                 "bge": int(v1) >= int(v2),
                 "bltu": (v1 & 0xffffffff) < (v2 & 0xffffffff),  # unsigned
                 "bgeu": (v1 & 0xffffffff) >= (v2 & 0xffffffff)
             }[op]
     ```

3. BPUDecoder
   - Lightweight decoder that classifies instructions quickly:
     - Conditional branch (B-type)
     - Indirect jump (jalr)
     - Unconditional jump (jal)
   - Avoids full, heavyweight decode in Stage 1 to reduce latency.

---

## Classes & high-level behavior

- BranchPrecomputationUnit
  - Orchestrates Stage 1 and Stage 2.
  - Communicates with pipeline registers (IF/ID/EX/MEM/WB) for forwarded data.
  - Emits directives (e.g., IC.Directive) for immediate PC redirection on taken branches.

Main methods (high-level):
- _run_bpu_stage1(pc, fetch_packets)
  - Pre-decodes next two fetched instructions.
  - Computes BTAs with MinimalALU.
  - Checks hazards/dependencies and sets stall requests.
  - Enqueues candidate branch(s) for Stage 2 evaluation.

- _run_bpu_stage2(enqueued_branches, regfile, forwarded_values)
  - Evaluates branch conditions with Comparator using best-available operand values.
  - Decides taken/not-taken and returns redirect target if taken.

- run_bpu_cycle(...)
  - Calls Stage 1 and Stage 2 appropriately each cycle.
  - Integrates with fetch logic to redirect PC on taken branches.
  - Provides early forwarding information to ID stage if available.

---

## Pipeline integration

- The BPU runs ahead of decode, creating a "branch pre-decode window".
- If Stage 1 finds an unconditional jump (jal), the BPU immediately signals a redirect.
- For conditional branches, Stage 1 enqueues candidates; Stage 2 evaluates them as soon as operands are available (including forwarded values).
- The BPU can request pipeline stalls when it detects load-use hazards or missing forwarded data necessary to resolve a branch safely.

---

## Instruction memory and labels

- Supports all base RV32I instruction formats:
  - R-type, I-type, S-type, B-type, U-type, J-type.
- Branch/jump labels (e.g., beq x1, x2, loop) are resolved to absolute PC addresses via a label dictionary (label_dict) during assembly/load time.

---

## Directory structure

Root summary:
```
├── README.md                       # Project documentation (this file)
└── code/                           # Source files
   ├── Instruction_class.py         # Instruction object representation and field decoding
   ├── component_def.py             # Register file, memory, ALU, pipeline register definitions
   ├── stages_def.py                # Implementation of pipeline stages (IF, ID, EX, MEM, WB)
   ├── full_pipeline_risc32i.py     # Main pipeline simulator integrating all modules
   └── test_instruction.py          # Simple harness to load assembly and run the simulator
```

---

## Getting started

Prerequisites:
- Python 3.8+ (recommended)
- No external packages required unless introduced later

Quick setup:
1. Clone the repository:
   ```
   git clone https://github.com/MRIDHUL22041889/Branch_precomputation.git
   cd Branch_precomputation
   ```
2. Inspect the code in the `code/` directory.

---

## Running the simulator

To run the basic test harness:
```
python3 code/test_instruction.py
```

This script will load example assembly (if provided) and run the pipeline simulator, demonstrating BPU behavior and effects on fetch/redirection.

For more advanced experiments:
- Edit test instruction sequences in `test_instruction.py`.
- Adjust pipeline and BPU parameters inside `full_pipeline_risc32i.py` and `component_def.py`.

---

## To_do
--Not verified and tested for heavy dependencies , need to be fixed.
--Need to do proper benchmarking.

---

## License

This project is provided "as-is". Add a LICENSE file in the repository root to make your preferred license explicit (e.g., MIT, Apache-2.0).

---

Author: MRIDHUL22041889
Source: https://github.com/MRIDHUL22041889/Branch_precomputation/blob/f858312c333893edd200430f656e211982c94c1f/README.md
