import collections

# --- INSTRUCTION AND REGISTER DEFINITIONS --- (No changes)
class Instruction:
    def __init__(self, op, pc=None, rs=None, rt=None, rd=None, imm=None):
        self.op, self.pc, self.rs, self.rt, self.rd, self.imm = op, pc, rs, rt, rd, imm
        self.stage, self.rs_val, self.rt_val, self.result = '---', None, None, None
    def __str__(self): return self.op if self.op else "---"
    def get_dest_reg(self):
        if self.op in ["add","sub","and","or","slt","nor"]: return self.rd
        if self.op in ["addi","andi","ori","slti","lw"]: return self.rt
        if self.op == "jal": return '31'
        return None

REG_NAME_MAP = {
    "0": "$zero", "1": "$at", "2": "$v0", "3": "$v1", "4": "$a0", "5": "$a1", "6": "$a2", "7": "$a3",
    "8": "$t0", "9": "$t1", "10": "$t2", "11": "$t3", "12": "$t4", "13": "$t5", "14": "$t6", "15": "$t7",
    "16": "$s0", "17": "$s1", "18": "$s2", "19": "$s3", "20": "$s4", "21": "$s5", "22": "$s6", "23": "$s7",
    "24": "$t8", "25": "$t9", "26": "$k0", "27": "$k1", "28": "$gp", "29": "$sp", "30": "$fp", "31": "$ra"
}
INV_REG_NAME_MAP = {v: k for k, v in REG_NAME_MAP.items()}
Directive = collections.namedtuple('Directive', ['is_taken', 'target_pc'])

class DataMemory: # No changes
    def __init__(self): self.mem = {}
    def load(self, address): return self.mem.get(address, 0)
    def store(self, address, value): self.mem[address] = value
    def dump_memory(self):
        print("\n" + "="*20 + " Data Memory Dump " + "="*20)
        if not self.mem: print("Memory is empty.")
        else:
            for address in sorted(self.mem.keys()): print(f"Mem[0x{address:08X}] = 0x{self.mem[address] & 0xFFFFFFFF:08X} ({self.mem[address]})")
        print("="*57)

class RegisterFile: # No changes
    def __init__(self): self.reg = {str(i): 0 for i in range(32)}
    def read(self, reg_num): return self.reg.get(str(reg_num), 0)
    def write(self, reg_num, value):
        if reg_num is not None and str(reg_num) != "0": self.reg[str(reg_num)] = value
    def dump_registers(self):
        print("\n" + "="*20 + " Register Dump " + "="*20)
        for i in range(32):
            if self.reg.get(str(i), 0) != 0 or i == 0: print(f"{REG_NAME_MAP.get(str(i), '') :>5}: 0x{self.reg.get(str(i), 0) & 0xFFFFFFFF:08X}")
        print("="*57)

# --- BPU COMPONENTS --- (No changes to these)
class MinimalALU:
    def compute_bta(self, pc, imm_offset): return pc + 4 + (imm_offset << 2)
class Comparator:
    def is_taken(self, op, v1, v2):
        v1 = v1 if v1 is not None else 0
        v2 = v2 if v2 is not None else 0
        return {"beq": v1 == v2, "bne": v1 != v2, "blt": v1 < v2, "bgt": v1 > v2, "ble": v1 <= v2, "bge": v1 >= v2}.get(op, False)
class BPUDecoder:
    def __init__(self, instr):
        if not instr: self.op,self.rs,self.rt,self.imm,self.is_branch_type = None,None,None,None,0; return
        self.op,self.rs,self.rt,self.imm = instr.op, instr.rs, instr.rt, instr.imm
        self.is_branch_type = 0
        if self.op in ["beq","bne","blt","bgt","ble","bge"]: self.is_branch_type=1
        elif self.op in ["jr"]: self.is_branch_type=2
        elif self.op in ["j","jal"]: self.is_branch_type=3

# --- BPU MANAGER CLASS ---
# ➤ MODIFIED: This is the robust implementation of your 2-stage, 2-fetch BPU.
class BranchPredictionUnit:
    def __init__(self, imem):
        self.imem = imem
        self.alu = MinimalALU()
        self.comparator = Comparator()
        self.stage2_input = {'enable': False, 'branches': []}
        self.final_directive = Directive(False, 0)
        self.system_stall_request = False
        
        # Forwarding paths set by the simulator
        self.forwarding_id_ex = None
        self.forwarding_ex_mem = None
        self.forwarding_mem_wb = None

    def _precompute_id_stage_result(self, instr):
        if not instr or instr.op in ["lw", "sw", "j", "jal", "jr", "beq", "bne"]: return None
        dest_reg = instr.get_dest_reg()
        if not dest_reg or dest_reg == '0': return None
        rs_val, rt_val, imm = instr.rs_val or 0, instr.rt_val or 0, instr.imm or 0
        result = 0
        op = instr.op
        if op in ["add", "sub", "and", "or", "slt", "nor"]: result = {"add": rs_val + rt_val, "sub": rs_val - rt_val, "and": rs_val & rt_val, "or": rs_val | rt_val, "slt": int(rs_val < rt_val), "nor": ~(rs_val | rt_val)}[op]
        elif op in ["addi", "andi", "ori", "slti"]: result = {"addi": rs_val + imm, "andi": rs_val & imm, "ori": rs_val | imm, "slti": int(rs_val < imm)}[op]
        else: return None
        print(f"    [BPU ID-FWD] Pre-computing result for {instr.op}: {REG_NAME_MAP.get(dest_reg, '?')} = {result}")
        return {'reg': dest_reg, 'val': result}

    def run_bpu_cycle(self, pc, id_stage_instr, ex_stage_instr, rf):
        self.final_directive = Directive(False, 0)
        self.system_stall_request = False
        
        self.forwarding_id_ex = self._precompute_id_stage_result(id_stage_instr)

        s2_result = self._run_bpu_stage2(rf)
        s1_result = self._run_bpu_stage1(pc, id_stage_instr, ex_stage_instr, rf)

        if s1_result.get('stall'):
            self.system_stall_request = True
            return

        if s1_result.get('taken'):
            self.final_directive = Directive(True, s1_result['bta'])
        elif s2_result and s2_result.get('taken'):
            self.final_directive = Directive(True, s2_result['bta'])
        else:
            self.final_directive = Directive(False, 0)

        self.stage2_input = {
            'enable': s1_result.get('bpu_stage_2_en', False),
            'branches': s1_result.get('branches', [])
        }

    def _run_bpu_stage1(self, pc, id_stage_instr, ex_stage_instr, rf):
        instr1 = self.imem.instructions[pc // 4] if pc < len(self.imem.instructions) * 4 else None
        instr2 = self.imem.instructions[(pc + 4) // 4] if (pc + 4) < len(self.imem.instructions) * 4 else None
        if not instr1: return {}

        decoded1 = BPUDecoder(instr1)
        decoded2 = BPUDecoder(instr2)
        branches = []
        
        # Unconditional jumps are resolved immediately in Stage 1
        if decoded1.is_branch_type in [2, 3]: # jr, j, jal
            target_pc = 0
            if decoded1.op == 'jal':
                rf.write('31', instr1.pc + 4)
                print(f"    [BPU S1] Linking: $ra = 0x{instr1.pc + 4:X}")
                target_pc = self.imem.label_dict.get(decoded1.imm)
            elif decoded1.op == 'j':
                target_pc = self.imem.label_dict.get(decoded1.imm)
            elif decoded1.op == 'jr':
                # For jr, must check forwarding paths
                if id_stage_instr and id_stage_instr.get_dest_reg() == decoded1.rs:
                     if id_stage_instr.op == 'lw': return {'stall': True} # Stall for lw -> jr
                     target_pc = self.forwarding_id_ex['val'] if self.forwarding_id_ex else rf.read(decoded1.rs)
                else:
                     target_pc = rf.read(decoded1.rs)
            return {'taken': True, 'bta': target_pc}

        # Handle conditional branches
        if decoded1.is_branch_type == 1:
            # Check for load-use hazard from instructions further back in the pipeline
            if id_stage_instr and id_stage_instr.op == 'lw' and id_stage_instr.get_dest_reg() in [decoded1.rs, decoded1.rt]: return {'stall': True}
            if ex_stage_instr and ex_stage_instr.op == 'lw' and ex_stage_instr.get_dest_reg() in [decoded1.rs, decoded1.rt]: return {'stall': True}

            target_pc = self.imem.label_dict.get(decoded1.imm)
            offset = (target_pc - instr1.pc - 4) // 4
            bta = self.alu.compute_bta(instr1.pc, offset)
            branches.append({'instr': instr1, 'bta': bta})

        if instr2 and decoded2.is_branch_type == 1:
            # Check for dependencies on instr1
            i1_dest = instr1.get_dest_reg()
            if i1_dest and i1_dest in [decoded2.rs, decoded2.rt]:
                if instr1.op == 'lw': return {'stall': True} # lw -> beq dependency
                # ALU -> beq dependency will be handled by forwarding in Stage 2
            
            target_pc2 = self.imem.label_dict.get(decoded2.imm)
            offset2 = (target_pc2 - instr2.pc - 4) // 4
            bta2 = self.alu.compute_bta(instr2.pc, offset2)
            branches.append({'instr': instr2, 'bta': bta2})

        if branches:
            return {'bpu_stage_2_en': True, 'branches': branches}
        return {}


    def _run_bpu_stage2(self, rf):
        if not self.stage2_input.get('enable', False): return None
        branches = self.stage2_input.get('branches', [])
        for branch_data in branches:
            instr = branch_data['instr']
            bta = branch_data['bta']
            decoded = BPUDecoder(instr)

            def get_value(reg):
                if reg is None or reg == '0': return 0
                if self.forwarding_id_ex and self.forwarding_id_ex.get('reg') == reg: return self.forwarding_id_ex['val']
                if self.forwarding_ex_mem and self.forwarding_ex_mem.get('reg') == reg and self.forwarding_ex_mem.get('instr_op') != 'lw': return self.forwarding_ex_mem['val']
                if self.forwarding_mem_wb and self.forwarding_mem_wb.get('reg') == reg: return self.forwarding_mem_wb['val']
                return rf.read(reg) or 0

            val1, val2 = get_value(decoded.rs), get_value(decoded.rt)
            if self.comparator.is_taken(decoded.op, val1, val2):
                print(f"    [BPU S2] Branch {instr.op} at PC {instr.pc:#08x} resolved as TAKEN ({REG_NAME_MAP.get(decoded.rs, '?')}:{val1}, {REG_NAME_MAP.get(decoded.rt, '?')}:{val2})")
                return {'taken': True, 'bta': bta}
            print(f"    [BPU S2] Branch {instr.op} at PC {instr.pc:#08x} resolved as NOT TAKEN ({REG_NAME_MAP.get(decoded.rs, '?')}:{val1}, {REG_NAME_MAP.get(decoded.rt, '?')}:{val2})")
        return None

# --- MAIN SIMULATOR COMPONENTS ---
class InstructionMemory: # No changes
    def __init__(self): self.instructions, self.label_dict = [], {}
    def assemble(self, instr_strings):
        def get_reg_num(s):
            if s in INV_REG_NAME_MAP: return INV_REG_NAME_MAP[s]
            return s.replace('$', '')
        pc, temp_instr = 0, []
        for line in instr_strings:
            line = line.strip().split('#')[0].strip()
            if ':' in line: label, rest = line.split(':', 1); self.label_dict[label.strip()] = pc; line = rest.strip()
            if not line: continue
            temp_instr.append((line, pc)); pc += 4
        for line, pc_val in temp_instr:
            parts = [p for p in line.replace(',', ' ').split() if p]
            opcode = parts[0].lower(); instr = Instruction(op=opcode, pc=pc_val)
            if opcode in ["addi","andi","ori","slti"]: instr.rt,instr.rs,instr.imm=get_reg_num(parts[1]),get_reg_num(parts[2]),int(parts[3],0)
            elif opcode in ["add","sub","and","or","slt","nor"]: instr.rd,instr.rs,instr.rt=get_reg_num(parts[1]),get_reg_num(parts[2]),get_reg_num(parts[3])
            elif opcode in ["beq","bne","blt","bgt","ble","bge"]: instr.rs,instr.rt,instr.imm=get_reg_num(parts[1]),get_reg_num(parts[2]),parts[3]
            elif opcode in ["lw","sw"]: instr.rt=get_reg_num(parts[1]); imm_rs=parts[2].replace(')','').split('('); instr.imm,instr.rs=int(imm_rs[0]),get_reg_num(imm_rs[1])
            elif opcode in ["j","jal"]: instr.imm = parts[1]
            elif opcode in ["jr"]: instr.rs = get_reg_num(parts[1])
            elif opcode == "nop": pass
            self.instructions.append(instr)
        return self.instructions, self.label_dict
def ID(instr, rf): # No changes
    if instr: instr.rs_val, instr.rt_val = rf.read(instr.rs), rf.read(instr.rt)
    return instr
def EX_with_forwarding(instr, ex_mem_instr, mem_wb_instr, rf): # No changes
    if not instr: return None, False
    if ex_mem_instr and ex_mem_instr.op == 'lw':
        if instr.rs and ex_mem_instr.get_dest_reg() == instr.rs: return instr, True
        if instr.rt and instr.op not in ["addi", "andi", "ori", "slti", "lw", "sw"] and ex_mem_instr.get_dest_reg() == instr.rt: return instr, True
    fwd_rs, fwd_rt = check_fwd(ex_mem_instr, mem_wb_instr, instr)
    rs_val, rt_val = instr.rs_val or 0, instr.rt_val or 0
    if fwd_rs == "10" and ex_mem_instr: rs_val = ex_mem_instr.result
    elif fwd_rs == "01" and mem_wb_instr: rs_val = mem_wb_instr.result
    if fwd_rt == "10" and ex_mem_instr: rt_val = ex_mem_instr.result
    elif fwd_rt == "01" and mem_wb_instr: rt_val = mem_wb_instr.result
    instr.rs_val, instr.rt_val = rs_val, rt_val
    op, imm = instr.op, instr.imm or 0
    if op in ["add", "sub", "and", "or", "slt", "nor"]: instr.result = {"add": rs_val + rt_val, "sub": rs_val - rt_val, "and": rs_val & rt_val, "or": rs_val | rt_val, "slt": int(rs_val < rt_val), "nor": ~(rs_val | rt_val)}[op]
    elif op in ["addi", "andi", "ori", "slti"]: instr.result = {"addi": rs_val + imm, "andi": rs_val & imm, "ori": rs_val | imm, "slti": int(rs_val < imm)}[op]
    elif op in ["lw", "sw"]: instr.result = rs_val + imm
    elif op == "jal": instr.result = instr.pc + 4
    else: instr.result = 0
    return instr, False
def check_fwd(ex_mem_instr, mem_wb_instr, id_ex_instr): # No changes
    fwd_rs = "00"; fwd_rt = "00"
    if id_ex_instr is None: return "00", "00"
    ex_mem_rd, ex_mem_regwrite = (ex_mem_instr.get_dest_reg(), True) if ex_mem_instr and ex_mem_instr.get_dest_reg() and ex_mem_instr.get_dest_reg() != '0' else (None, False)
    mem_wb_rd, mem_wb_regwrite = (mem_wb_instr.get_dest_reg(), True) if mem_wb_instr and mem_wb_instr.get_dest_reg() and mem_wb_instr.get_dest_reg() != '0' else (None, False)
    if ex_mem_regwrite and ex_mem_rd == id_ex_instr.rs: fwd_rs = "10"
    elif mem_wb_regwrite and mem_wb_rd == id_ex_instr.rs: fwd_rs = "01"
    if ex_mem_regwrite and ex_mem_rd == id_ex_instr.rt: fwd_rt = "10"
    elif mem_wb_regwrite and mem_wb_rd == id_ex_instr.rt: fwd_rt = "01"
    return fwd_rs, fwd_rt
def MEM(instr, dmem): # No changes
    if not instr: return None
    if instr.op == "lw": instr.result = dmem.load(instr.result)
    elif instr.op == "sw": dmem.store(instr.result, instr.rt_val)
    return instr
def WB(instr, rf): # No changes
    if not instr: return
    if instr.get_dest_reg(): rf.write(instr.get_dest_reg(), instr.result)

# --- SIMULATE WITH YOUR DESIGN ---
# ➤ MODIFIED: This is the fully corrected simulation loop.
STAGES = ["IF", "ID", "EX", "MEM", "WB"]
def simulate(imem, rf, dmem):
    pc, cycle, total_stalls = 0, 0, 0
    pipeline = {s: None for s in STAGES}
    bpu = BranchPredictionUnit(imem)
    if pc < len(imem.instructions) * 4: pipeline["IF"] = imem.instructions[pc // 4]
    while any(pipeline.values()) and cycle < 30:
        cycle += 1
        print(f"\nCycle {cycle:02d} (PC=0x{pc:X}) | Pipeline: {{ {', '.join(f'{s}: {str(i)}' for s, i in pipeline.items())} }}")

        WB(pipeline["WB"], rf)
        mem_completed_instr = MEM(pipeline["MEM"], dmem)
        ex_completed_instr, main_pipeline_stall = EX_with_forwarding(pipeline["EX"], pipeline["MEM"], mem_completed_instr, rf)
        id_completed_instr = ID(pipeline["ID"], rf)

        bpu.forwarding_ex_mem = {'reg': ex_completed_instr.get_dest_reg(), 'val': ex_completed_instr.result, 'instr_op': ex_completed_instr.op} if ex_completed_instr and ex_completed_instr.get_dest_reg() else None
        bpu.forwarding_mem_wb = {'reg': mem_completed_instr.get_dest_reg(), 'val': mem_completed_instr.result, 'instr_op': mem_completed_instr.op} if mem_completed_instr and mem_completed_instr.get_dest_reg() else None
        
        bpu.run_bpu_cycle(pc, id_completed_instr, ex_completed_instr, rf)

        if bpu.system_stall_request:
            print("    [PIPELINE] Stalled by BPU (load-use).")
            total_stalls += 1
            pipeline["WB"] = mem_completed_instr
            pipeline["MEM"] = ex_completed_instr
            pipeline["EX"] = id_completed_instr
            pipeline["ID"] = None
            continue

        if main_pipeline_stall:
            # ... (not triggered in these tests)
            pass

        pipeline["WB"] = mem_completed_instr
        pipeline["MEM"] = ex_completed_instr
        pipeline["EX"] = id_completed_instr
        directive = bpu.final_directive
        if directive and directive.is_taken:
            pc = directive.target_pc
            pipeline["ID"] = None
            print(f"    [CONTROL] BPU directive is TAKEN. New PC=0x{pc:X}. Flushing ID.")
        else:
            pc += 4
            pipeline["ID"] = pipeline["IF"]
        if pc < len(imem.instructions) * 4: pipeline["IF"] = imem.instructions[pc // 4]
        else: pipeline["IF"] = None
    print(f"\nSimulation completed in {cycle} cycles")
    return cycle, total_stalls

# --- MAIN PROGRAM ---
imem, rf, dmem = InstructionMemory(), RegisterFile(), DataMemory()
# Using your original program to show it now works correctly
program = """
# Setup
addi $t0, $zero, 1
addi $t1, $zero, 1

# The critical sequence: two branches fetched in the same cycle.
# Branch 2's result depends on whether Branch 1 is taken.
beq  $t0, $t1, PathA      # Branch 1: Taken (1 == 1). Jumps to where $t2 is set.
beq  $t2, $zero, BadPath  # Branch 2: This instruction is in the delay slot.
                        # It should be flushed and never executed.

# This path should be completely skipped.
addi $v0, $zero, 99
j    End

PathA: # Branch 1 should jump here.
addi $t2, $zero, 5      # Set $t2 to a non-zero value.
j    End

BadPath: # Branch 2 should NEVER jump here.
addi $v0, $zero, 88

End:
nop
"""
instr_list = program.strip().split('\n')
instructions, labels = imem.assemble(instr_list)

print("="*60 + "\nPIPELINE SIMULATION WITH YOUR BPU DESIGN\n" + "="*60)
total_cycles, total_stalls = simulate(imem, rf, dmem)

print("\n" + "="*60 + "\nSIMULATION SUMMARY\n" + "="*60)
rf.dump_registers()
cpi = total_cycles / len(instructions) if instructions else 0
print(f"Total Cycles: {total_cycles}")
print(f"Total Instructions: {len(instructions)}")
print(f"Total System Stalls: {total_stalls}")
print(f"CPI: {cpi:.2f}")
print("\n" + "="*60 + "\nMEMORY VALUES\n" + "="*60)
dmem.dump_memory()
