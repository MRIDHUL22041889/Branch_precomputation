program = """
_start:
    addi x5, x0, 5      # x5 = 5
    addi x6, x0, 5      # x6 = 5
    beq  x5, x6, taken  # branch taken
    addi x7, x0, 1      # (not executed)
    j    done
taken:
    addi x7, x0, 2      # x7 = 2
done:
    nop
"""