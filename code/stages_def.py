
def ID(instr, rf):
    if instr: instr.rs1_val, instr.rs2_val = rf.read(instr.rs1), rf.read(instr.rs2)
    return instr

def EX_with_forwarding(instr, ex_mem_instr, mem_wb_instr, alu):
    if not instr:
        # We now return None directly, not a tuple
        return None

    # NO STALL DETECTION HERE ANYMORE
    
    rs1_val, rs2_val = instr.rs1_val, instr.rs2_val
    fwd_rs1, fwd_rs2 = check_fwd(ex_mem_instr, mem_wb_instr, instr)
    
    if fwd_rs1 == "10": rs1_val = ex_mem_instr.result
    elif fwd_rs1 == "01": rs1_val = mem_wb_instr.result
    
    if fwd_rs2 == "10": rs2_val = ex_mem_instr.result
    elif fwd_rs2 == "01": rs2_val = mem_wb_instr.result
    
    instr.result = alu.execute(instr, instr.pc, rs1_val, rs2_val)
    
    # We now return only the completed instruction
    return instr

def check_fwd(ex_mem_instr, mem_wb_instr, id_ex_instr):
    fwd_rs1, fwd_rs2 = "00", "00"
    if id_ex_instr is None:
        return "00", "00"

    # Get destination registers, ensuring they are not None and not the zero register
    ex_mem_rd = ex_mem_instr.get_dest_reg() if ex_mem_instr and ex_mem_instr.get_dest_reg() != '0' else None
    mem_wb_rd = mem_wb_instr.get_dest_reg() if mem_wb_instr and mem_wb_instr.get_dest_reg() != '0' else None

    # --- THIS IS THE CRITICAL LOGIC ---

    # Priority 1: Forward from the MEM stage (EX-MEM register)
    # This handles ALU -> ALU dependencies
    if ex_mem_rd:
        if ex_mem_rd == id_ex_instr.rs1:
            fwd_rs1 = "10"
        if ex_mem_rd == id_ex_instr.rs2:
            fwd_rs2 = "10"
    
    # Priority 2: Forward from the WB stage (MEM-WB register)
    # This handles ALU -> ALU over a gap, and the CRITICAL case of LW -> ALU after a stall.
    if mem_wb_rd:
        # Only forward if a closer source (from EX/MEM) was not already found
        if mem_wb_rd == id_ex_instr.rs1 and fwd_rs1 == "00":
            fwd_rs1 = "01"
        if mem_wb_rd == id_ex_instr.rs2 and fwd_rs2 == "00":
            fwd_rs2 = "01"
            
    # --- TEMPORARY DEBUG PRINT ---
    if id_ex_instr.op == "addi" and id_ex_instr.rd == "29": # t4 is x29, t5 is x30
        print(f"[FWD_DEBUG] Checking for addi t5: rs1={id_ex_instr.rs1}, FWD_CODE={fwd_rs1}")
    # ---------------------------

    return fwd_rs1, fwd_rs2

def MEM(instr, dmem, rf, ex_mem_instr=None, mem_wb_instr=None):
    if not instr:
        return None

    op = instr.op
    addr = instr.result # For loads/stores, this is the memory address

    load_opcodes = ["lw", "lh", "lb", "lbu", "lhu"]
    store_opcodes = ["sw", "sh", "sb"]

    if op in load_opcodes:
        instr.result = dmem.load(addr, {"lw": 4, "lh": 2, "lb": 1, "lhu": 2, "lbu": 1}[op], "u" not in op)
    
    elif op in store_opcodes:
        val_to_store = rf.read(instr.rs2) 
        _, fwd_rs2 = check_fwd(ex_mem_instr, mem_wb_instr, instr)
        if fwd_rs2 == "10": val_to_store = ex_mem_instr.result
        elif fwd_rs2 == "01": val_to_store = mem_wb_instr.result
        
        dmem.store(addr, val_to_store, {"sw": 4, "sh": 2, "sb": 1}[op])

    elif op in ["ecall", "ebreak"]:
        print(f"    [SYSTEM] Encountered {op} at PC 0x{instr.pc:X}")

    return instr

def WB(instr, rf):
    if instr and instr.op == "jal":
        print(f"[WB STAGE JAL DEBUG] rd={instr.rd}, result={instr.result}, get_dest_reg() returns: {instr.get_dest_reg()}")
    if instr and instr.get_dest_reg(): rf.write(instr.get_dest_reg(), instr.result)
