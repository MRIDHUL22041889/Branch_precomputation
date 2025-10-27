import collections
import Instruction_class as IC
import component_def as cd
import stages_def as stg   
# --- SIMULATOR ---
STAGES = ["IF", "ID", "EX", "MEM", "WB"]



def simulate(imem, rf, dmem):
    pc, cycle, total_stalls = 0, 0, 0
    pipeline = {s: None for s in STAGES}
    alu = cd.RISCV_ALU()
    bpu = cd.BranchPrecomputationUnit(imem, alu) 
    
    if pc < len(imem.instructions) * 4:
        pipeline["IF"] = imem.instructions[pc // 4]
        
    while any(pipeline.values()):
        cycle += 1
        print(f"\nCycle {cycle:02d} (PC=0x{pc:X}) | Pipeline: {{ {', '.join(f'{s}: {str(i)}' for s, i in pipeline.items())} }}")

        # --- Pipeline stages execute in reverse order ---
        stg.WB(pipeline["WB"], rf)
        mem_completed_instr = stg.MEM(pipeline["MEM"], dmem, rf, pipeline["EX"], pipeline["WB"])
        
        # EX stage now ONLY does forwarding and execution. It no longer signals stalls.
        ex_completed_instr = stg.EX_with_forwarding(pipeline["EX"], pipeline["MEM"], pipeline["WB"], alu)
        
        id_completed_instr = stg.ID(pipeline["ID"], rf)

        # --- NEW: ID STAGE HAZARD DETECTION ---
        # This logic runs AFTER the ID stage but BEFORE the pipeline advances.
        # It checks if the instruction LEAVING ID depends on a load in the EX stage.
        hazard_stall = False
        load_opcodes = ["lw", "lb", "lh", "lbu", "lhu"]
        
        instr_in_EX = pipeline["EX"] # This is the instruction that just finished its ID stage
        instr_in_ID = pipeline["ID"] # This is the instruction currently in the ID stage
        
        # The classic load-use hazard: instr in ID needs the result of instr in EX
        if instr_in_EX and instr_in_EX.op in load_opcodes:
            dest_reg = instr_in_EX.get_dest_reg()
            if dest_reg and instr_in_ID:
                if dest_reg in [instr_in_ID.rs1, instr_in_ID.rs2]:
                    # This check is more specific to the simulator's structure
                    # where the instruction to be stalled is the one in ID
                    hazard_stall = True
        
        # --- THE CORRECTED STALL HANDLER ---
        if hazard_stall:
            print("    [PIPELINE] Load-use hazard STALL (ID stage).")
            total_stalls += 1
            
            # Advance the back-end of the pipeline
            pipeline["WB"] = mem_completed_instr
            pipeline["MEM"] = ex_completed_instr
            
            # Inject a bubble into EX, holding the dependent instruction in ID.
            pipeline["EX"] = None 
            # pipeline["ID"] is NOT changed.
            # pipeline["IF"] is NOT changed.
            # PC is NOT changed.
            
            # Use 'continue' to restart the loop, effectively re-processing the ID/IF stages
            continue

        # --- Update BPU forwarding paths for the *next* cycle ---
        # This must be done AFTER the stall check
        bpu.forwarding_ex_mem = {'reg': ex_completed_instr.get_dest_reg(), 'val': ex_completed_instr.result, 'instr_op': ex_completed_instr.op} if ex_completed_instr else None
        bpu.forwarding_mem_wb = {'reg': mem_completed_instr.get_dest_reg(), 'val': mem_completed_instr.result, 'instr_op': mem_completed_instr.op} if mem_completed_instr else None
        bpu.run_bpu_cycle(pc, id_completed_instr, ex_completed_instr, rf)

        # --- BPU STALL HANDLER (for branch dependencies) ---
        if bpu.system_stall_request:
            print("    [PIPELINE] Stalled by BPU (branch dependency).")
            total_stalls += 1
            # Advance pipeline but keep PC the same and nullify ID
            pipeline["WB"] = mem_completed_instr
            pipeline["MEM"] = ex_completed_instr
            pipeline["EX"] = id_completed_instr
            pipeline["ID"] = None
            bpu.last_checked_pc = None # Force BPU to re-evaluate next cycle
            continue

        # --- If no stalls, advance the pipeline normally ---
        pipeline["WB"] = mem_completed_instr
        pipeline["MEM"] = ex_completed_instr
        pipeline["EX"] = id_completed_instr
        
        # --- Control Flow and Fetch ---
        directive = bpu.final_directive
        if directive and directive.is_taken:
            pc = directive.target_pc
            pipeline["ID"] = None # Flush the instruction that was just decoded
            print(f"    [CONTROL] BPU directive is TAKEN. New PC=0x{pc:X}. Flushing ID.")
        else:
            pc += 4
            pipeline["ID"] = pipeline["IF"] # Advance IF to ID
            
        bpu.last_checked_pc = None # Reset check for new PC

        # Fetch the next instruction
        if pc < len(imem.instructions) * 4:
            pipeline["IF"] = imem.instructions[pc // 4]
        else:
            pipeline["IF"] = None
    
    print(f"\nSimulation completed in {cycle} cycles")
    return cycle, total_stalls


# --- MAIN PROGRAM ---
imem, rf, dmem = cd.InstructionMemory(), cd.RegisterFile(), cd.DataMemory()
# A comprehensive program to test the full RV32I ISA implementation
import test_instruction as ti
instr_list = ti.program.strip().split('\n')
instructions, labels = imem.assemble(instr_list)

print("="*60 + "\nPIPELINE SIMULATION WITH RISC-V 32I ISA\n" + "="*60)
total_cycles, total_stalls = simulate(imem, rf, dmem)

print("\n" + "="*60 + "\nSIMULATION SUMMARY\n" + "="*60)
cpi = total_cycles / len(instructions) if instructions else 0
print(f"Total Cycles: {total_cycles}")
print(f"Total Instructions Executed: {len(instructions)}")
print(f"Total System Stalls: {total_stalls}")
print(f"CPI: {cpi:.2f}")

rf.dump_registers()
dmem.dump_memory()