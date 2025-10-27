import Instruction_class as IC
import collections
class DataMemory:
    """Simulates the data memory unit with byte-addressable read/write."""
    def __init__(self):
        self.mem = {}

    def load(self, address, num_bytes, signed):
        """Loads 1, 2, or 4 bytes from memory."""
        val = 0
        for i in range(num_bytes):
            byte = self.mem.get(address + i, 0)
            val |= byte << (i * 8)

        if signed:
            bit_width = num_bytes * 8
            sign_bit = 1 << (bit_width - 1)
            if (val & sign_bit) != 0:
                val -= (1 << bit_width)
        return val

    def store(self, address, value, num_bytes):
        """Stores 1, 2, or 4 bytes to memory."""
        for i in range(num_bytes):
            byte = (value >> (i * 8)) & 0xFF
            self.mem[address + i] = byte

    def dump_memory(self):
        print("\n" + "="*20 + " Data Memory Dump " + "="*20)
        if not self.mem:
            print("Memory is empty.")
        else:
            # Group by words for readability
            words = {}
            for addr in self.mem.keys():
                word_addr = addr & ~3
                if word_addr not in words:
                    words[word_addr] = [0, 0, 0, 0]
            for addr, byte in self.mem.items():
                word_addr = addr & ~3
                byte_offset = addr & 3
                words[word_addr][byte_offset] = byte
            
            for address in sorted(words.keys()):
                word_val = (words[address][3] << 24 | words[address][2] << 16 |
                            words[address][1] << 8 | words[address][0])
                print(f"Mem[0x{address:08X}] = 0x{word_val & 0xFFFFFFFF:08X}")
        print("="*57)

class RegisterFile:
    """Simulates the RISC-V 32-register file."""
    def __init__(self):
        self.reg = {str(i): 0 for i in range(32)}

    def read(self, reg_num):
        return self.reg.get(str(reg_num), 0)

    def write(self, reg_num, value):
        if reg_num is not None and str(reg_num) != "0":
            self.reg[str(reg_num)] = value

    def dump_registers(self):
        print("\n" + "="*20 + " Register Dump " + "="*20)
        important = ["1", "2", "10", "11"]  # ra, sp, a0, a1
        printed_regs = set()
        for reg_num_str in important:
            val = self.reg.get(reg_num_str, 0)
            print(f"{IC.REG_NAME_MAP.get(reg_num_str, ''):>5} (x{reg_num_str}): 0x{val & 0xFFFFFFFF:08X}")
            printed_regs.add(reg_num_str)

        for i in range(32):
            reg_num_str = str(i)
            if reg_num_str in printed_regs: continue
            val = self.reg.get(reg_num_str)
            if (val is not None and val != 0) or i == 0:
                print(f"{IC.REG_NAME_MAP.get(reg_num_str, ''):>5} (x{i}): 0x{val & 0xFFFFFFFF:08X}")
        print("="*57)

# --- BPU COMPONENTS (UNCHANGED CORE LOGIC) ---
class MinimalALU:
    """A minimal ALU for BPU's Branch Target Address calculation."""
    def compute_bta(self, pc, imm_offset): return pc + imm_offset
class Comparator:
    """A comparator for resolving conditional branches in the BPU."""
    def is_taken(self, op, v1, v2):
        v1, v2 = v1 or 0, v2 or 0
        return {"beq": v1 == v2, "bne": v1 != v2, "blt": v1 < v2, "bge": v1 >= v2,
                "bltu": (v1 & 0xFFFFFFFF) < (v2 & 0xFFFFFFFF),
                "bgeu": (v1 & 0xFFFFFFFF) >= (v2 & 0xFFFFFFFF)}.get(op, False)
class BPUDecoder:
    """Decodes instructions to determine if they are branch/jump types for the BPU."""
    def __init__(self, instr):
        if not instr: self.op, self.rs1, self.rs2, self.imm, self.is_branch_type = None, None, None, None, 0; return
        self.op, self.rs1, self.rs2, self.imm = instr.op, instr.rs1, instr.rs2, instr.imm
        self.is_branch_type = 0
        if self.op in ["beq", "bne", "blt", "bge", "bltu", "bgeu"]: self.is_branch_type = 1
        elif self.op in ["jalr"]: self.is_branch_type = 2
        elif self.op in ["jal"]: self.is_branch_type = 3
# --- BPU MANAGER CLASS (UNCHANGED CORE LOGIC) ---
class BranchPrecomputationUnit:
    def __init__(self, imem,alu):
        self.imem = imem
        self.main_alu =alu            # The powerful ALU for pre-computing results
        self.alu = MinimalALU()         # The simple ALU for BTA calculation
        self.comparator = Comparator()
        self.stage2_input = {'enable': False, 'branches': []}
        self.final_directive = IC.Directive(False, 0)
        self.system_stall_request, self.last_checked_pc = False, None
        self.forwarding_id_ex, self.forwarding_ex_mem, self.forwarding_mem_wb = None, None, None
    def _precompute_id_stage_result(self, instr):
        if not instr or instr.op in [
            "lb", "lh", "lw", "lbu", "lhu",        # Loads
            "sb", "sh", "sw",                      # Stores
            "beq", "bne", "blt", "bge", "bltu", "bgeu", # Branches
            "jal", "jalr",                         # Jumps
            "ecall", "ebreak", "nop"]: return None
        dest_reg = instr.get_dest_reg()
        if not dest_reg or dest_reg == '0': return None
        result = self.main_alu.execute(instr, instr.pc, instr.rs1_val, instr.rs2_val)
        print(f"    [BPU ID-FWD] Pre-computing result for '{instr.op}' (PC={instr.pc:#x}): reg {dest_reg} = {result}")
        return {'reg': dest_reg, 'val': result}


    def run_bpu_cycle(self, pc, id_stage_instr, ex_stage_instr, rf):
        # Reset outputs at the start of every cycle
        self.final_directive = IC.Directive(False, 0)
        self.system_stall_request = False
        if self.last_checked_pc == pc:
            s1_result = self.stage2_input 
        else:
            s1_result = self._run_bpu_stage1(pc, id_stage_instr, ex_stage_instr, rf)
        
        self.last_checked_pc = pc
        if s1_result.get('stall'):
            self.system_stall_request = True
            self.stage2_input = {'branches': s1_result.get('branches', [])}
            return
        if s1_result.get('taken'):
            self.final_directive = IC.Directive(True, s1_result['bta'])
            self.stage2_input = {'enable': False, 'branches': []} # Clear any old state
            return
        self.forwarding_id_ex = self._precompute_id_stage_result(id_stage_instr)
        branches_to_check = s1_result.get('branches', [])
        s2_result = self._run_bpu_stage2(rf, branches_to_check)

        # If Stage 2 resolved a branch as TAKEN, we are done for this cycle.
        if s2_result and s2_result.get('taken'):
            self.final_directive = IC.Directive(True, s2_result['bta'])
            self.stage2_input = {'enable': False, 'branches': []}
            return
        self.final_directive = IC.Directive(False, 0)
        self.stage2_input = {'branches': branches_to_check}


    def _run_bpu_stage1(self, pc, id_stage_instr, ex_stage_instr, rf):
        instr1 = self.imem.instructions[pc // 4] if pc < len(self.imem.instructions) * 4 else None
        instr2 = self.imem.instructions[(pc + 4) // 4] if (pc + 4) < len(self.imem.instructions) * 4 else None
        print(f"    [BPU S1] instr1.pc={getattr(instr1, 'pc', None)}, instr2.pc={getattr(instr2, 'pc', None)}")
        if not instr1: return {}
        decoded1, decoded2, branches = BPUDecoder(instr1), BPUDecoder(instr2), []
        if decoded1.is_branch_type == 3: return {'taken': True, 'bta': self.imem.label_dict.get(decoded1.imm)}
        if decoded1.op == 'jalr' or decoded1.is_branch_type == 1:
            use_regs = [decoded1.rs1, decoded1.rs2] if decoded1.is_branch_type == 1 else [decoded1.rs1]
            if any(id_stage_instr and id_stage_instr.op == 'lw' and id_stage_instr.get_dest_reg() == r for r in use_regs) or \
               any(ex_stage_instr and ex_stage_instr.op == 'lw' and ex_stage_instr.get_dest_reg() == r for r in use_regs):
                return {'stall': True}
            bta = self.alu.compute_bta(instr1.pc, self.imem.label_dict.get(decoded1.imm) - instr1.pc) if decoded1.is_branch_type == 1 else 0
            branches.append({'instr': instr1, 'bta': bta})
        if instr2 and decoded2.is_branch_type == 1:
            i1_dest = instr1.get_dest_reg()
            if i1_dest and i1_dest in [decoded2.rs1, decoded2.rs2] and instr1.op == 'lw': return {'stall': True}
            bta2 = self.alu.compute_bta(instr2.pc, self.imem.label_dict.get(decoded2.imm) - instr2.pc)
            branches.append({'instr': instr2, 'bta': bta2})
        return {'bpu_stage_2_en': True, 'branches': branches} if branches else {}

    def _run_bpu_stage2(self, rf, branches_to_check): # <-- Added 'branches_to_check' argument
        # The 'if not self.stage2_input...' line is REMOVED.
        
        def get_value(reg):
            # (This inner function does not change at all)
            if reg is None or reg == '0': return 0
            if self.forwarding_id_ex and self.forwarding_id_ex.get('reg') == reg: return self.forwarding_id_ex['val']
            if self.forwarding_ex_mem and self.forwarding_ex_mem.get('reg') == reg and 'lw' not in (self.forwarding_ex_mem.get('instr_op') or ""): return self.forwarding_ex_mem['val']
            if self.forwarding_mem_wb and self.forwarding_mem_wb.get('reg') == reg: return self.forwarding_mem_wb['val']
            return rf.read(reg) or 0
            
        for branch in branches_to_check: # <-- Use the new argument here
            instr, bta, decoded = branch['instr'], branch['bta'], BPUDecoder(branch['instr'])
            if decoded.op == 'jalr':
                target = (get_value(decoded.rs1) + (decoded.imm or 0)) & ~1
                print(f"    [BPU S2] JALR at PC {instr.pc:#08x} resolved to 0x{target:X}"); return {'taken': True, 'bta': target}
            val1, val2 = get_value(decoded.rs1), get_value(decoded.rs2)
            if self.comparator.is_taken(decoded.op, val1, val2):
                print(f"    [BPU S2] Branch {instr.op} resolved as TAKEN"); return {'taken': True, 'bta': bta}
            print(f"    [BPU S2] Branch {instr.op} resolved as NOT TAKEN")
        return None

# --- MAIN SIMULATOR COMPONENTS ---
class InstructionMemory:
    """Parses RISC-V assembly and stores instructions."""
    def __init__(self):
        self.instructions, self.label_dict = [], {}

    def assemble(self, instr_strings):
        def get_reg_num(s): return IC.INV_REG_NAME_MAP.get(s, s.replace('x', ''))
        pc, temp_instr = 0, []
        for line in instr_strings:
            line = line.strip().split('#')[0].strip()
            if ':' in line: label, rest = line.split(':', 1); self.label_dict[label.strip()] = pc; line = rest.strip()
            if not line: continue
            temp_instr.append((line, pc)); pc += 4
            
        for line, pc_val in temp_instr:
            # --- FIX IS HERE ---
            # We no longer replace the comma globally. We split into opcode and the rest.
            parts = [p.strip() for p in line.split(maxsplit=1)]
            opcode = parts[0].lower()
            operands_str = parts[1] if len(parts) > 1 else ""
            
            # Now, we split the operands string by the comma. This is more robust.
            operands = [p.strip() for p in operands_str.split(',')]
            
            instr = IC.Instruction(op=opcode, pc=pc_val)
            
            if opcode in ["add","sub","xor","or","and","sll","slt","sltu","srl","sra"]: instr.rd, instr.rs1, instr.rs2 = map(get_reg_num, operands)
            elif opcode in ["addi","xori","ori","andi","slti","sltiu","slli","srli","srai"]: instr.rd, instr.rs1, instr.imm = get_reg_num(operands[0]), get_reg_num(operands[1]), int(operands[2], 0)
            elif opcode in ["lb", "lh", "lw", "lbu", "lhu"]: instr.rd, mem_operand = get_reg_num(operands[0]), operands[1]; mem_parts = mem_operand.replace(')','').split('('); instr.imm, instr.rs1 = int(mem_parts[0]), get_reg_num(mem_parts[1])
            elif opcode == "jalr": instr.rd, instr.rs1 = get_reg_num(operands[0]), get_reg_num(operands[1]); instr.imm = int(operands[2], 0) if len(operands) > 2 else 0
            elif opcode in ["sb", "sh", "sw"]: instr.rs2, mem_operand = get_reg_num(operands[0]), operands[1]; mem_parts = mem_operand.replace(')','').split('('); instr.imm, instr.rs1 = int(mem_parts[0]), get_reg_num(mem_parts[1])
            elif opcode in ["beq","bne","blt","bge","bltu","bgeu"]: instr.rs1, instr.rs2, instr.imm = get_reg_num(operands[0]), get_reg_num(operands[1]), operands[2]
            elif opcode in ["lui", "auipc"]: instr.rd, instr.imm = get_reg_num(operands[0]), int(operands[1], 0)
            elif opcode == "jal": instr.rd, instr.imm = get_reg_num(operands[0]), operands[1]
            elif opcode in ["nop", "ecall", "ebreak"]: pass
            
            self.instructions.append(instr)
        return self.instructions, self.label_dict
    
class RISCV_ALU:
    """Encapsulates all RISC-V execution logic."""
    def execute(self, instr, pc, rs1_val, rs2_val):
        op, imm = instr.op, instr.imm or 0
        rs1_val, rs2_val = rs1_val or 0, rs2_val or 0
        ops = {
            "add": lambda: rs1_val + rs2_val, "sub": lambda: rs1_val - rs2_val,
            "xor": lambda: rs1_val ^ rs2_val, "or": lambda: rs1_val | rs2_val,
            "and": lambda: rs1_val & rs2_val, "sll": lambda: rs1_val << (rs2_val & 0x1F),
            "slt": lambda: 1 if rs1_val < rs2_val else 0,
            "sltu": lambda: 1 if (rs1_val & 0xFFFFFFFF) < (rs2_val & 0xFFFFFFFF) else 0,
            "srl": lambda: (rs1_val & 0xFFFFFFFF) >> (rs2_val & 0x1F),
            "sra": lambda: rs1_val >> (rs2_val & 0x1F),
            "addi": lambda: rs1_val + imm, "xori": lambda: rs1_val ^ imm,
            "ori": lambda: rs1_val | imm, "andi": lambda: rs1_val & imm,
            "slti": lambda: 1 if rs1_val < imm else 0,
            "sltiu": lambda: 1 if (rs1_val & 0xFFFFFFFF) < (imm & 0xFFFFFFFF) else 0,
            "slli": lambda: rs1_val << (imm & 0x1F),
            "srli": lambda: (rs1_val & 0xFFFFFFFF) >> (imm & 0x1F),
            "srai": lambda: rs1_val >> (imm & 0x1F),
            "lb": lambda: rs1_val + imm, "lh": lambda: rs1_val + imm, "lw": lambda: rs1_val + imm,
            "lbu": lambda: rs1_val + imm, "lhu": lambda: rs1_val + imm,
            "sb": lambda: rs1_val + imm, "sh": lambda: rs1_val + imm, "sw": lambda: rs1_val + imm,
            "jalr": lambda: rs1_val + imm,
            "auipc": lambda: pc + (imm << 12), "lui": lambda: imm << 12,
            "jal": lambda: pc + 4, "ecall": lambda: 0, "ebreak": lambda: 0
        }
        return ops.get(op, lambda: 0)()
