##  Branch Precomputation Unit (BPU)
# Concept Overview

Modern processor faces significant challenges in handling control hazards due to branch instruction especially data dependent branch instructions. This leads to stall, pipeline flushes or mispredicted paths this lead to reduced performance and throughput in Inorder processors.

Modern high performance processors use history based dynamic predictors for branch prediction like TAGE which are not suitable for low power and are constraint inorder processors and they also struggle in resolving data dependent branches. In systems for low power application they usually employ a one cycle penality model or two bit dynamic branch predictors.

Instead of waiting for the ID/EX stage to evaluate branch conditions, the BPU:

Pre-decodes and identifies branch/jump instructions early (Stage 1).

Resolves their outcomes using forwarded or register values (Stage 2).

Redirects the PC immediately when a branch is determined taken — avoiding unnecessary pipeline bubbles.

This design allows simultaneous evaluation of two upcoming instructions and early branch target calculation, which improves fetch efficiency and reduces branch penalty cycles.

 # Design Architecture

The BPU consists of three main component types and one control manager:

1️⃣ BTA Commuter

A lightweight arithmetic unit used to pre-compute Branch Target Addresses (BTAs):

class MinimalALU:
    def compute_bta(self, pc, imm_offset):
        return pc + imm_offset


This avoids stalling the main ALU for simple PC+offset operations.

2️⃣ Comparator

Evaluates branch conditions such as beq, bne, blt, etc.
It supports both signed and unsigned comparisons:

class Comparator:
    def is_taken(self, op, v1, v2):
        return {"beq": v1 == v2, "bne": v1 != v2, ...}[op]

3️⃣ BPUDecoder

A lightweight instruction decoder that identifies whether an instruction is:

A conditional branch (type 1)

A jump (jalr, type 2)

An unconditional jump (jal, type 3)
This helps Stage 1 quickly classify instructions without full decode.

# BranchPrecomputationUnit 

This class orchestrates both precomputation stages and interacts with the pipeline registers.

Stage 1 – Pre-Decoding and Dependency Check (_run_bpu_stage1)

-Fetches two consecutive instructions (instr1, instr2).

-Detects whether either is a branch or jump.

-Computes Branch Target Addresses (BTAs) for them.

-Checks for dependencies with instructions in the ID and EX stages (especially load-use hazards).

-If a dependency exists → requests a stall.

-If an unconditional jump (jal) is found → immediately marks taken with the computed BTA.

Stage 2 – Branch Evaluation (_run_bpu_stage2)

-Resolves branch conditions using:

--Register File values,

--Forwarded data from ID/EX/MEM/WB stages,

--Or precomputed ALU results.

-If the branch is taken → returns the redirect target PC (BTA).

--Otherwise → execution continues normally.

# Pipeline Integration (run_bpu_cycle)

The run_bpu_cycle() method integrates both stages within each clock cycle:

Stage 1 runs when a new PC is fetched.

If dependency-free, Stage 2 evaluates previously queued branches.

If a branch resolves taken, it emits a final directive (IC.Directive) to the fetch unit for immediate redirection.

Simultaneously, the BPU precomputes results for the current ID-stage instruction to support early forwarding.

This means the BPU runs ahead of the decode stage — effectively creating a “branch pre-decode window.”

# InstructionMemory Integration

Supports all base RV32I instruction formats:

R-type (add, sub, etc.)

I-type (addi, lw, etc.)

S-type (sw, sb, etc.)

B-type (beq, bne, etc.)

U-type (lui, auipc)

J-type (jal, jalr)

Labels in branch or jump operands (e.g. beq x1, x2, loop) are resolved into absolute PC addresses via the label_dict.

# Directory Structure 
├── README.md # Project documentation (this file)
└── code/ # All source files
   ├── Instruction_class.py # Instruction object representation and field decoding
   ├── component_def.py # Definitions for register file, memory, ALU, and pipeline registers
   ├── stages_def.py # Implementation of pipeline stages (IF, ID, EX, MEM, WB)
   ├── full_pipeline_risc32i.py # Main pipeline simulator integrating all modules
   ├── test_instruction.py # Load the asm to run here
