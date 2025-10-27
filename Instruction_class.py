# --- INSTRUCTION AND REGISTER DEFINITIONS ---
import collections
class Instruction:
    """Represents a RISC-V instruction with its fields and pipeline state."""
    def __init__(self, op, pc=None, rs1=None, rs2=None, rd=None, imm=None):
        self.op, self.pc, self.rs1, self.rs2, self.rd, self.imm = \
            op, pc, rs1, rs2, rd, imm
        self.stage, self.rs1_val, self.rs2_val, self.result = '---', None, None, None

    def __str__(self):
        return self.op if self.op else "---"

    def get_dest_reg(self):
        """Returns the destination register number based on the instruction type."""
        if self.op in [
            "add", "sub", "xor", "or", "and", "sll", "slt", "sltu", "srl", "sra",
            "addi", "xori", "ori", "andi", "slli", "srli", "srai", "slti", "sltiu",
            "auipc", "lui", "lb", "lh", "lw", "lbu", "lhu", "jal", "jalr"
        ]:
            return self.rd
        return None

# RISC-V Application Binary Interface (ABI) Register Names
REG_NAME_MAP = {
    "0": "zero", "1": "ra", "2": "sp", "3": "gp", "4": "tp", "5": "t0", "6": "t1", "7": "t2",
    "8": "s0", "9": "s1", "10": "a0", "11": "a1", "12": "a2", "13": "a3", "14": "a4", "15": "a5",
    "16": "a6", "17": "a7", "18": "s2", "19": "s3", "20": "s4", "21": "s5", "22": "s6", "23": "s7",
    "24": "s8", "25": "s9", "26": "s10", "27": "s11", "28": "t3", "29": "t4", "30": "t5", "31": "t6"
}
INV_REG_NAME_MAP = {v: k for k, v in REG_NAME_MAP.items()}
Directive = collections.namedtuple('Directive', ['is_taken', 'target_pc'])

