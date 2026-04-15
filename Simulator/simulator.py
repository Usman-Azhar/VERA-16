import os
import sys
import customtkinter as ctk

# Configurations for UI
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Constants
OPCODES = {
    "ADD": 0b00000, "SUB": 0b00001, "MUL": 0b00010, "AND": 0b00011,
    "OR":  0b00100, "XOR": 0b00101, "MOV": 0b00110, "CMP": 0b00111,
    "NOT": 0b01000, "INC": 0b01001, "DEC": 0b01010, "SHL": 0b01011,
    "SHR": 0b01100, "LDI": 0b01101, "LDM": 0b01110, "STM": 0b01111,
    "JMP": 0b10000, "JZ":  0b10001, "JNZ": 0b10010, "HLT": 0b10011,
    "INP": 0b10100, "OUT": 0b10101, "SKI": 0b10110, "SKO": 0b10111,
    "ION": 0b11000, "IOF": 0b11001, "CLA": 0b11110, "CMR": 0b11110,
    "CLC": 0b11110, "STC": 0b11110, "CLZ": 0b11110, "NOP": 0b11110,
    "SWAP":0b11110
}

REG_MAP = {"R0":0, "R1":1, "R2":2, "R3":3, "R4":4, "R5":5, "R6":6, "R7":7}

class CPU:
    def __init__(self):
        self.reset()
        
    def reset(self):
        self.memory = [0] * 4096
        self.R = [0] * 8
        self.PC = 0
        self.IR = 0
        self.TR = 0
        self.AR = 0
        self.DR = 0
        self.SC = 0
        
        self.Z = 0
        self.C = 0
        self.N = 0
        self.IEN = 0
        self.FGI = 0
        self.FGO = 0
        self.S = 1
        
        self.INPR = 0
        self.OUTR = 0
        self.halted = False
        
        self.changed_reg = None  # to highlight
        
    def get_reg(self, token):
        token = token.upper().strip()
        if token in REG_MAP:
            return REG_MAP[token]
        else:
            raise ValueError(f"Unknown register {token}")

    def assemble(self, code_text):
        self.reset()
        lines = code_text.strip().split('\n')
        addr = 0
        logs = []
        assembled_lines = []
        for i, line in enumerate(lines):
            line_clean = line.split(';')[0].strip().replace(',', ' ')
            if not line_clean:
                assembled_lines.append(None)
                continue
                
            parts = line_clean.split()
            mnemonic = parts[0].upper()
            if mnemonic not in OPCODES:
                raise ValueError(f"Line {i+1}: Unknown instruction '{mnemonic}'")
            
            opcode = OPCODES[mnemonic]
            mode = 0
            dst = 0
            src = 0
            
            try:
                if mnemonic in ["ADD", "SUB", "MUL", "AND", "OR", "XOR", "MOV", "CMP"]:
                    dst = self.get_reg(parts[1])
                    src = self.get_reg(parts[2])
                elif mnemonic in ["NOT", "INC", "DEC"]:
                    dst = self.get_reg(parts[1])
                elif mnemonic in ["SHL", "SHR"]:
                    mode = 1
                    dst = self.get_reg(parts[1])
                    src = int(parts[2]) & 0x3F
                elif mnemonic == "LDI":
                    mode = 1
                    dst = self.get_reg(parts[1])
                    src = int(parts[2]) & 0x3F
                elif mnemonic in ["LDM", "STM"]:
                    mode = 3 # 11
                    dst = self.get_reg(parts[1])
                    src_str = parts[2].replace('[','').replace(']','')
                    src = self.get_reg(src_str)
                elif mnemonic == "JMP":
                    mode = 2
                    val = int(parts[1]) & 0x1FF
                    dst = (val >> 6) & 0x7
                    src = val & 0x3F
                elif mnemonic in ["JZ", "JNZ"]:
                    mode = 2
                    dst = self.get_reg(parts[1])
                    src = int(parts[2]) & 0x3F
                elif mnemonic in ["HLT", "INP", "OUT", "SKI", "SKO", "ION", "IOF"]:
                    mode = 2
                elif mnemonic in ["CLA", "CLC", "STC", "CLZ", "NOP"]:
                    if mnemonic == "CLA": dst = 4 # IR[8]=1
                    elif mnemonic == "CLC": dst = 1 # IR[6]=1
                    elif mnemonic == "STC": src = 32 # IR[5]=1
                    elif mnemonic == "CLZ": src = 16 # IR[4]=1
                    elif mnemonic == "NOP": src = 8  # IR[3]=1
                elif mnemonic == "CMR":
                    dst = 2 # IR[7]=1
                    src = self.get_reg(parts[1]) # store Rd in SRC[2:0]
                elif mnemonic == "SWAP":
                    mode = 3 # use mode 3 to avoid colliding with one hot decoding for regular 11110
                    dst = self.get_reg(parts[1])
                    src = self.get_reg(parts[2])
                    
                instr = (opcode << 11) | (mode << 9) | (dst << 6) | src
                self.memory[addr] = instr
                assembled_lines.append(addr)
                addr += 1
            except Exception as e:
                raise ValueError(f"Line {i+1}: Error parsing args for {mnemonic} - {str(e)}")
                
        return assembled_lines

    def update_flags_alu(self, val):
        self.Z = 1 if (val & 0xFFFF) == 0 else 0
        self.C = 1 if val > 0xFFFF else 0
        self.N = 1 if (val & 0x8000) != 0 else 0

    def step(self):
        if self.S == 0:
            return "Halted.", ""
            
        self.changed_reg = None
        self.AR = self.PC
        self.IR = self.memory[self.AR]
        self.PC = (self.PC + 1) & 0xFFF
        
        opcode = (self.IR >> 11) & 0x1F
        mode = (self.IR >> 9) & 0x03
        dst = (self.IR >> 6) & 0x07
        src = self.IR & 0x3F
        
        log_msg = f"PC={self.AR:03X} IR={self.IR:04X} -> "
        eng_msg = ""
        
        res = None
        dest_reg = dst
        update_flag = False
        old_dst = self.R[dst]
        old_src = self.R[src] if src < 8 else 0
        
        if opcode == 0b00000:
            res_full = self.R[dst] + self.R[src]
            self.R[dst] = res_full & 0xFFFF
            res = res_full
            update_flag = True
            log_msg += f"ADD R{dst}, R{src}"
            eng_msg = f"  Added R{dst} ({old_dst}) + R{src} ({old_src}) = {res_full}. Stored in R{dst}.  R{dst} = {self.R[dst]}"
        elif opcode == 0b00001:
            res_full = self.R[dst] + (~self.R[src] & 0xFFFF) + 1
            self.R[dst] = res_full & 0xFFFF
            res = res_full
            update_flag = True
            log_msg += f"SUB R{dst}, R{src}"
            eng_msg = f"  Subtracted R{src} ({old_src}) from R{dst} ({old_dst}) = {res_full}. Stored in R{dst}.  R{dst} = {self.R[dst]}"
        elif opcode == 0b00010:
            res_full = self.R[dst] * self.R[src]
            self.R[dst] = res_full & 0xFFFF
            res = res_full
            update_flag = True
            log_msg += f"MUL R{dst}, R{src}"
            eng_msg = f"  Multiplied R{dst} ({old_dst}) × R{src} ({old_src}) = {res_full}. Stored in R{dst}.  R{dst} = {self.R[dst]}"
        elif opcode == 0b00011:
            res_full = self.R[dst] & self.R[src]
            self.R[dst] = res_full & 0xFFFF
            res = res_full
            update_flag = True
            log_msg += f"AND R{dst}, R{src}"
            eng_msg = f"  Bitwise AND of R{dst} ({old_dst}) and R{src} ({old_src}) = {res_full}. Stored in R{dst}.  R{dst} = {self.R[dst]}"
        elif opcode == 0b00100:
            res_full = self.R[dst] | self.R[src]
            self.R[dst] = res_full & 0xFFFF
            res = res_full
            update_flag = True
            log_msg += f"OR R{dst}, R{src}"
            eng_msg = f"  Bitwise OR of R{dst} ({old_dst}) and R{src} ({old_src}) = {res_full}. Stored in R{dst}.  R{dst} = {self.R[dst]}"
        elif opcode == 0b00101:
            res_full = self.R[dst] ^ self.R[src]
            self.R[dst] = res_full & 0xFFFF
            res = res_full
            update_flag = True
            log_msg += f"XOR R{dst}, R{src}"
            eng_msg = f"  Bitwise XOR of R{dst} ({old_dst}) and R{src} ({old_src}) = {res_full}. Stored in R{dst}.  R{dst} = {self.R[dst]}"
        elif opcode == 0b00110:
            res_full = self.R[src]
            self.R[dst] = res_full & 0xFFFF
            res = res_full
            update_flag = True
            log_msg += f"MOV R{dst}, R{src}"
            eng_msg = f"  Copied value of R{src} ({old_src}) into R{dst}.  R{dst} = {self.R[dst]}"
        elif opcode == 0b00111:
            res_full = self.R[dst] + (~self.R[src] & 0xFFFF) + 1
            self.update_flags_alu(res_full)
            dest_reg = None
            log_msg += f"CMP R{dst}, R{src}"
            eng_msg = f"  Compared R{dst} ({old_dst}) and R{src} ({old_src}). Difference = {res_full}. Flags updated: Z={self.Z} C={self.C} N={self.N}"
        elif opcode == 0b01000:
            res_full = ~self.R[dst] & 0xFFFF
            self.R[dst] = res_full
            res = res_full
            update_flag = True
            log_msg += f"NOT R{dst}"
            eng_msg = f"  Flipped all bits of R{dst} ({old_dst}). Result = {res_full}. Stored in R{dst}."
        elif opcode == 0b01001:
            res_full = self.R[dst] + 1
            self.R[dst] = res_full & 0xFFFF
            res = res_full
            update_flag = True
            log_msg += f"INC R{dst}"
            eng_msg = f"  Incremented R{dst} by 1. Was {old_dst}, now {res_full}.  R{dst} = {self.R[dst]}"
        elif opcode == 0b01010:
            res_full = self.R[dst] + (~1 & 0xFFFF) + 1
            self.R[dst] = res_full & 0xFFFF
            res = res_full
            update_flag = True
            log_msg += f"DEC R{dst}"
            eng_msg = f"  Decremented R{dst} by 1. Was {old_dst}, now {res_full}.  R{dst} = {self.R[dst]}"
        elif opcode == 0b01011:
            shift = src & 0x0F
            res_full = self.R[dst] << shift
            self.R[dst] = res_full & 0xFFFF
            res = res_full
            update_flag = True
            log_msg += f"SHL R{dst}, {shift}"
            eng_msg = f"  Shifted R{dst} ({old_dst}) left by {shift} bits. Result = {res_full}. Stored in R{dst}.  R{dst} = {self.R[dst]}"
        elif opcode == 0b01100:
            shift = src & 0x0F
            res_full = self.R[dst] >> shift
            self.R[dst] = res_full & 0xFFFF
            res = res_full
            update_flag = True
            log_msg += f"SHR R{dst}, {shift}"
            eng_msg = f"  Shifted R{dst} ({old_dst}) right by {shift} bits. Result = {res_full}. Stored in R{dst}.  R{dst} = {self.R[dst]}"
        elif opcode == 0b01101:
            imm = src & 0x3F
            self.R[dst] = imm
            dest_reg = dst
            log_msg += f"LDI R{dst}, {imm}"
            eng_msg = f"  Loaded the number {imm} into register R{dst}.  R{dst} = {imm}"
        elif opcode == 0b01110:
            self.AR = self.R[src] & 0xFFF
            self.DR = self.memory[self.AR]
            self.R[dst] = self.DR
            dest_reg = dst
            log_msg += f"LDM R{dst}, [R{src}]"
            eng_msg = f"  Loaded value from memory address R{src} (address={self.R[src]}). R{dst} = {self.R[dst]}."
        elif opcode == 0b01111:
            self.AR = self.R[dst] & 0xFFF
            self.memory[self.AR] = self.R[src]
            dest_reg = None
            log_msg += f"STM [R{dst}], R{src}"
            eng_msg = f"  Stored value of R{src} ({self.R[src]}) into memory at address R{dst} ({self.R[dst]})."
        elif opcode == 0b10000:
            addr = ((dst << 6) | src) & 0x1FF
            self.PC = addr
            dest_reg = None
            log_msg += f"JMP {addr}"
            eng_msg = f"  Jumped to address {addr}. PC is now {addr}."
        elif opcode == 0b10001:
            imm = src & 0x3F
            dest_reg = None
            log_msg += f"JZ R{dst}, {imm}"
            if self.R[dst] == 0:
                self.PC = imm
                eng_msg = f"  Checked if R{dst} = 0. It was zero. Jumped to {imm}."
            else:
                eng_msg = f"  Checked if R{dst} = 0. It was not zero. Did not jump."
        elif opcode == 0b10010:
            imm = src & 0x3F
            dest_reg = None
            log_msg += f"JNZ R{dst}, {imm}"
            if self.R[dst] != 0:
                self.PC = imm
                eng_msg = f"  Checked if R{dst} ≠ 0. It was not zero. Jumped to {imm}."
            else:
                eng_msg = f"  Checked if R{dst} ≠ 0. It was zero. Did not jump."
        elif opcode == 0b10011:
            self.S = 0
            self.halted = True
            dest_reg = None
            log_msg += "HLT"
            eng_msg = "  CPU halted. Program finished."
        elif opcode == 0b10100:
            self.R[0] = self.INPR
            self.FGI = 0
            dest_reg = 0
            log_msg += "INP"
            eng_msg = f"  Read input value ({self.INPR}) into R0."
        elif opcode == 0b10101:
            self.OUTR = self.R[0] & 0xFF
            self.FGO = 0
            dest_reg = None
            log_msg += "OUT"
            eng_msg = f"  Sent R0 value ({self.R[0]}) to output device."
        elif opcode == 0b10110:
            old_fgi = self.FGI
            dest_reg = None
            log_msg += "SKI"
            if self.FGI == 1:
                self.PC = (self.PC + 1) & 0xFFF
                eng_msg = f"  Checked input flag (FGI). It was {old_fgi}. Skipped next instruction."
            else:
                eng_msg = f"  Checked input flag (FGI). It was {old_fgi}. Continued."
        elif opcode == 0b10111:
            old_fgo = self.FGO
            dest_reg = None
            log_msg += "SKO"
            if self.FGO == 1:
                self.PC = (self.PC + 1) & 0xFFF
                eng_msg = f"  Checked output flag (FGO). It was {old_fgo}. Skipped next instruction."
            else:
                eng_msg = f"  Checked output flag (FGO). It was {old_fgo}. Continued."
        elif opcode == 0b11000:
            self.IEN = 1
            dest_reg = None
            log_msg += "ION"
            eng_msg = "  Interrupts enabled."
        elif opcode == 0b11001:
            self.IEN = 0
            dest_reg = None
            log_msg += "IOF"
            eng_msg = "  Interrupts disabled."
        elif opcode == 0b11110:
            dest_reg = None
            if mode == 3:
                temp = self.R[dst]
                self.R[dst] = self.R[src]
                self.R[src] = temp
                self.changed_reg = (dst, src)
                log_msg += f"SWAP R{dst}, R{src}"
                eng_msg = f"  Swapped values of R{dst} and R{src}. R{dst} is now {self.R[dst]}, R{src} is now {self.R[src]}."
            else:
                if (self.IR >> 8) & 1:
                    self.R[0] = 0
                    dest_reg = 0
                    log_msg += "CLA"
                    eng_msg = "  Cleared R0 to zero."
                elif (self.IR >> 7) & 1:
                    rd = src & 0x07
                    self.R[rd] = ~self.R[rd] & 0xFFFF
                    self.Z = 1 if self.R[rd] == 0 else 0
                    self.N = 1 if (self.R[rd] & 0x8000) else 0
                    dest_reg = rd
                    log_msg += f"CMR R{rd}"
                    eng_msg = f"  Complemented all bits of R{rd}. Result stored in R{rd}."
                elif (self.IR >> 6) & 1:
                    self.C = 0
                    log_msg += "CLC"
                    eng_msg = "  Carry flag cleared to 0."
                elif (self.IR >> 5) & 1:
                    self.C = 1
                    log_msg += "STC"
                    eng_msg = "  Carry flag set to 1."
                elif (self.IR >> 4) & 1:
                    self.Z = 0
                    log_msg += "CLZ"
                    eng_msg = "  Zero flag cleared to 0."
                elif (self.IR >> 3) & 1:
                    log_msg += "NOP"
                    eng_msg = "  No operation. Nothing happened."
        
        if update_flag and res is not None:
            self.update_flags_alu(res)
            
        if dest_reg is not None:
            if getattr(self, 'changed_reg', None) is None:
                self.changed_reg = dest_reg

        if self.IEN == 1 and (self.FGI == 1 or self.FGO == 1):
            self.TR = self.PC
            self.memory[0] = self.TR
            self.PC = 1
            self.IEN = 0
            
        return log_msg, eng_msg

class SimulatorApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        self.title("VERA-16 Simulator")
        self.geometry("1100x700")
        self.resizable(True, True)
        self.configure(fg_color="#1e1e1e")
        
        self.cpu = CPU()
        self.step_count = 0
        self.running = False
        self.assembled_lines = []
        
        self.grid_columnconfigure(0, weight=0, minsize=320)
        self.grid_columnconfigure(1, weight=1, minsize=420)
        self.grid_columnconfigure(2, weight=0, minsize=300)
        self.grid_rowconfigure(0, weight=1)
        
        self.create_left_panel()
        self.create_middle_panel()
        self.create_right_panel()
        
        self.load_test_program()
        self.update_ui()
        
    def create_left_panel(self):
        frame = ctk.CTkFrame(self, fg_color="#2d2d2d", corner_radius=0)
        frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        
        lbl_title = ctk.CTkLabel(frame, text="VERA-16 Simulator", font=("Consolas", 20, "bold"), text_color="#d4d4d4")
        lbl_title.pack(pady=10)
        
        # REGISTERS
        ctk.CTkLabel(frame, text="REGISTERS", font=("Consolas", 14, "bold"), text_color="#4fc3f7").pack(pady=(10,5))
        reg_frame = ctk.CTkFrame(frame, fg_color="transparent")
        reg_frame.pack()
        self.reg_labels = {}
        for i in range(8):
            r_img = ctk.CTkLabel(reg_frame, text=f"R{i}: 0000h  ", font=("Consolas", 14), text_color="#ffffff")
            r_img.grid(row=i//2, column=i%2, padx=10, pady=5)
            self.reg_labels[i] = r_img
            
        # SPECIAL
        ctk.CTkLabel(frame, text="SPECIAL REGISTERS", font=("Consolas", 14, "bold"), text_color="#4fc3f7").pack(pady=(20,5))
        spec_frame = ctk.CTkFrame(frame, fg_color="transparent")
        spec_frame.pack()
        self.spec_labels = {}
        spec_keys = ['PC','IR','TR','AR','DR','SC']
        for i, k in enumerate(spec_keys):
            lbl = ctk.CTkLabel(spec_frame, text=f"{k}: 0000h", font=("Consolas", 14), text_color="#ffffff")
            lbl.grid(row=i//2, column=i%2, padx=10, pady=5, sticky="w")
            self.spec_labels[k] = lbl
            
        # FLAGS
        ctk.CTkLabel(frame, text="FLAGS & FLIP-FLOPS", font=("Consolas", 14, "bold"), text_color="#4fc3f7").pack(pady=(20,5))
        flag_frame = ctk.CTkFrame(frame, fg_color="transparent")
        flag_frame.pack()
        self.flag_labels = {}
        for f in ['Z', 'C', 'N', 'IEN', 'FGI', 'FGO', 'S']:
            lbl = ctk.CTkLabel(flag_frame, text=f"{f}=0", font=("Consolas", 12), text_color="#ffffff")
            lbl.pack(side="left", padx=5)
            self.flag_labels[f] = lbl
        
        # IO
        ctk.CTkLabel(frame, text="I/O REGISTERS", font=("Consolas", 14, "bold"), text_color="#4fc3f7").pack(pady=(20,5))
        io_frame = ctk.CTkFrame(frame, fg_color="transparent")
        io_frame.pack()
        self.inpr_label = ctk.CTkLabel(io_frame, text="INPR: 00h", font=("Consolas", 14), text_color="#ffffff")
        self.inpr_label.grid(row=0, column=0, padx=10)
        self.outr_label = ctk.CTkLabel(io_frame, text="OUTR: 00h", font=("Consolas", 14), text_color="#ffffff")
        self.outr_label.grid(row=0, column=1, padx=10)

    def create_middle_panel(self):
        frame = ctk.CTkFrame(self, fg_color="#2d2d2d", corner_radius=0)
        frame.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        
        ctk.CTkLabel(frame, text="ASSEMBLY CODE", font=("Consolas", 14, "bold"), text_color="#4fc3f7").pack(pady=(10,5))
        
        self.code_editor = ctk.CTkTextbox(frame, font=("Consolas", 14), fg_color="#1e1e1e", text_color="#d4d4d4", height=300)
        self.code_editor.pack(fill="x", padx=10)
        
        self.code_editor._textbox.tag_configure("highlight", background="#1a3a5c")
        
        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.pack(pady=10)
        
        self.btn_assemble = ctk.CTkButton(btn_frame, text="ASSEMBLE", font=("Consolas", 12, "bold"), fg_color="#0d47a1", hover_color="#1565c0", width=80, command=self.do_assemble)
        self.btn_assemble.grid(row=0, column=0, padx=5)
        
        self.btn_step = ctk.CTkButton(btn_frame, text="STEP", font=("Consolas", 12, "bold"), fg_color="#0d47a1", hover_color="#1565c0", width=80, command=self.do_step, state="disabled")
        self.btn_step.grid(row=0, column=1, padx=5)
        
        self.btn_run = ctk.CTkButton(btn_frame, text="RUN", font=("Consolas", 12, "bold"), fg_color="#0d47a1", hover_color="#1565c0", width=80, command=self.do_run, state="disabled")
        self.btn_run.grid(row=0, column=2, padx=5)
        
        self.btn_reset = ctk.CTkButton(btn_frame, text="RESET", font=("Consolas", 12, "bold"), fg_color="#0d47a1", hover_color="#1565c0", width=80, command=self.do_reset)
        self.btn_reset.grid(row=0, column=3, padx=5)
        
        ctk.CTkLabel(frame, text="OUTPUT LOG", font=("Consolas", 14, "bold"), text_color="#4fc3f7").pack(pady=(10,5))
        self.log_viewer = ctk.CTkTextbox(frame, font=("Consolas", 12), fg_color="#1e1e1e", text_color="#a5d6a7", height=180)
        self.log_viewer.pack(fill="both", expand=True, padx=10, pady=(0,10))
        self.log_viewer._textbox.tag_configure("error", foreground="#ef9a9a")
        self.log_viewer.configure(state="disabled")

    def create_right_panel(self):
        frame = ctk.CTkFrame(self, fg_color="#2d2d2d", corner_radius=0)
        frame.grid(row=0, column=2, sticky="nsew", padx=10, pady=10)
        
        ctk.CTkLabel(frame, text="MEMORY VIEWER", font=("Consolas", 14, "bold"), text_color="#4fc3f7").pack(pady=(10,5))
        self.mem_textbox = ctk.CTkTextbox(frame, font=("Consolas", 14), fg_color="#1e1e1e", text_color="#d4d4d4", height=300)
        self.mem_textbox.pack(fill="x", padx=10)
        self.mem_textbox._textbox.tag_configure("highlight", background="#1a3a5c")
        
        ctk.CTkLabel(frame, text="INSTRUCTION REFERENCE", font=("Consolas", 14, "bold"), text_color="#4fc3f7").pack(pady=(20,5))
        self.ref_frame = ctk.CTkScrollableFrame(frame, fg_color="#1e1e1e", height=120)
        self.ref_frame.pack(fill="x", padx=10)
        
        mnemonics = ["ADD", "SUB", "MUL", "AND", "OR", "XOR", "MOV", "CMP", "NOT", "INC", "DEC", "SHL", "SHR", "LDI", "LDM", "STM", "JMP", "JZ", "JNZ", "HLT", "INP", "OUT", "SKI", "SKO", "ION", "IOF", "CLA", "CMR", "CLC", "STC", "CLZ", "NOP", "SWAP"]
        
        grid_f = ctk.CTkFrame(self.ref_frame, fg_color="transparent")
        grid_f.pack()
        for i, m in enumerate(mnemonics):
            b = ctk.CTkButton(grid_f, text=m, font=("Consolas",10), width=30, height=20, fg_color="transparent", hover_color="#444444", command=lambda x=m: self.show_desc(x))
            b.grid(row=i//4, column=i%4, padx=2, pady=2)
            
        self.desc_label = ctk.CTkLabel(frame, text="Click an instruction to see details.", font=("Consolas", 10), wraplength=260)
        self.desc_label.pack(pady=10, padx=10)
        
        self.descs = {
            "ADD": "ADD Rd, Rs -> Rd = Rd + Rs",
            "SUB": "SUB Rd, Rs -> Rd = Rd - Rs",
            "MUL": "MUL Rd, Rs -> Rd = Rd * Rs",
            "AND": "AND Rd, Rs -> Rd = Rd & Rs",
            "OR": "OR Rd, Rs -> Rd = Rd | Rs",
            "XOR": "XOR Rd, Rs -> Rd = Rd ^ Rs",
            "MOV": "MOV Rd, Rs -> Rd = Rs",
            "CMP": "CMP Rd, Rs -> temp = Rd - Rs, set Z/C/N flags",
            "NOT": "NOT Rd -> Rd = ~Rd",
            "INC": "INC Rd -> Rd = Rd + 1",
            "DEC": "DEC Rd -> Rd = Rd - 1",
            "SHL": "SHL Rd, #n -> Rd = Rd << n",
            "SHR": "SHR Rd, #n -> Rd = Rd >> n",
            "LDI": "LDI Rd, #imm -> Rd = imm",
            "LDM": "LDM Rd, [Rs] -> array load from Rs",
            "STM": "STM [Rd], Rs -> array store to Rd",
            "JMP": "JMP addr -> PC = addr",
            "JZ": "JZ Rd, addr -> IF Rd==0 PC = addr",
            "JNZ": "JNZ Rd, addr -> IF Rd!=0 PC = addr",
            "HLT": "HLT -> Stop execution",
            "INP": "INP -> R0 = INPR, FGI = 0",
            "OUT": "OUT -> OUTR = R0, FGO = 0",
            "SKI": "SKI -> IF FGI==1 PC = PC + 1",
            "SKO": "SKO -> IF FGO==1 PC = PC + 1",
            "ION": "ION -> Enable interrupt",
            "IOF": "IOF -> Disable interrupt",
            "CLA": "CLA -> R0 = 0",
            "CMR": "CMR Rd -> Rd = ~Rd, set Z/N",
            "CLC": "CLC -> C = 0",
            "STC": "STC -> C = 1",
            "CLZ": "CLZ -> Z = 0",
            "NOP": "NOP -> do nothing",
            "SWAP": "SWAP Rd, Rs -> Swap Rd and Rs"
        }

    def show_desc(self, m):
        self.desc_label.configure(text=self.descs.get(m, "No description."))

    def log(self, msg, is_error=False):
        self.log_viewer.configure(state="normal")
        self.log_viewer.insert("end", msg + "\n")
        if is_error:
            idx = self.log_viewer.index("end-2l")
            self.log_viewer._textbox.tag_add("error", idx, "end-1c")
        self.log_viewer.see("end")
        self.log_viewer.configure(state="disabled")
        
    def load_test_program(self):
        pgm = "LDI R0, 5\nLDI R1, 3\nADD R0, R1\nLDI R2, 10\nSUB R2, R0\nMOV R3, R2\nINC R3\nCMP R3, R1\nHLT\n"
        self.code_editor.insert("1.0", pgm)

    def do_assemble(self):
        code = self.code_editor.get("1.0", "end")
        try:
            self.assembled_lines = self.cpu.assemble(code)
            self.btn_step.configure(state="normal")
            self.btn_run.configure(state="normal")
            self.step_count = 0
            instr_count = len([x for x in self.assembled_lines if x is not None])
            self.log(f"Assembly successful! {instr_count} instructions loaded into memory.")
            self.log("────────────────────────────────────────")
            self.update_ui()
        except Exception as e:
            self.btn_step.configure(state="disabled")
            self.btn_run.configure(state="disabled")
            self.log(f"Assembly Error: {str(e)}", True)

    def highlight_code_line(self):
        self.code_editor._textbox.tag_remove("highlight", "1.0", "end")
        if getattr(self, 'assembled_lines', False):
            pc = self.cpu.PC
            try:
                line_idx = self.assembled_lines.index(pc)
                line_str = f"{line_idx+1}.0"
                self.code_editor._textbox.tag_add("highlight", line_str, line_str+" lineend")
            except ValueError:
                pass

    def update_ui(self, old_state=None):
        if old_state is None: old_state = {}
        def get_color(key, current_val):
            return "#ffeb3b" if key in old_state and old_state[key] != current_val else "#ffffff"

        for i in range(8):
            color = "#ffeb3b" if 'R' in old_state and old_state['R'][i] != self.cpu.R[i] else "#ffffff"
            self.reg_labels[i].configure(text=f"R{i}: {self.cpu.R[i]:04X}h  ", text_color=color)
            
        self.spec_labels['PC'].configure(text=f"PC:  {self.cpu.PC:03X}h", text_color=get_color('PC', self.cpu.PC))
        self.spec_labels['IR'].configure(text=f"IR:  {self.cpu.IR:04X}h", text_color=get_color('IR', self.cpu.IR))
        self.spec_labels['TR'].configure(text=f"TR:  {self.cpu.TR:04X}h", text_color=get_color('TR', self.cpu.TR))
        self.spec_labels['AR'].configure(text=f"AR:  {self.cpu.AR:03X}h", text_color=get_color('AR', self.cpu.AR))
        self.spec_labels['DR'].configure(text=f"DR:  {self.cpu.DR:04X}h", text_color=get_color('DR', self.cpu.DR))
        self.spec_labels['SC'].configure(text=f"SC:  T{self.cpu.SC}", text_color=get_color('SC', self.cpu.SC))
        
        for f in ['Z', 'C', 'N', 'IEN', 'FGI', 'FGO', 'S']:
            val = getattr(self.cpu, f)
            self.flag_labels[f].configure(text=f"{f}={val}", text_color=get_color(f, val))
        
        self.inpr_label.configure(text=f"INPR: {self.cpu.INPR:02X}h", text_color=get_color('INPR', self.cpu.INPR))
        self.outr_label.configure(text=f"OUTR: {self.cpu.OUTR:02X}h", text_color=get_color('OUTR', self.cpu.OUTR))
        
        self.highlight_code_line()
        
        self.mem_textbox.configure(state="normal")
        self.mem_textbox.delete("1.0", "end")
        for i in range(32):
            self.mem_textbox.insert("end", f"{i:03X}: {self.cpu.memory[i]:04X}h\n")
        
        self.mem_textbox._textbox.tag_remove("highlight", "1.0", "end")
        line_str = f"{self.cpu.PC + 1}.0"
        if self.cpu.PC < 32:
            self.mem_textbox._textbox.tag_add("highlight", line_str, line_str+" lineend")
        self.mem_textbox.configure(state="disabled")
        
    def do_step(self):
        if self.cpu.halted:
            return
            
        self.step_count += 1
        old_state = {
            'R': list(self.cpu.R), 'PC': self.cpu.PC, 'IR': self.cpu.IR, 'TR': self.cpu.TR,
            'AR': self.cpu.AR, 'DR': self.cpu.DR, 'SC': self.cpu.SC,
            'Z': self.cpu.Z, 'C': self.cpu.C, 'N': self.cpu.N,
            'IEN': self.cpu.IEN, 'FGI': self.cpu.FGI, 'FGO': self.cpu.FGO, 'S': self.cpu.S,
            'INPR': self.cpu.INPR, 'OUTR': self.cpu.OUTR
        }
        msg, eng_msg = self.cpu.step()
        self.log(f"[STEP {self.step_count}] " + msg)
        if eng_msg:
            self.log(eng_msg)
        self.log("────────────────────────────────────────")

        self.update_ui(old_state)
        if self.cpu.halted:
            self.log("════════════════════════════════════════")
            self.log("FINAL REGISTER STATE:")
            self.log(f"  R0 = {self.cpu.R[0]}    R1 = {self.cpu.R[1]}    R2 = {self.cpu.R[2]}    R3 = {self.cpu.R[3]}")
            self.log(f"  R4 = {self.cpu.R[4]}    R5 = {self.cpu.R[5]}    R6 = {self.cpu.R[6]}    R7 = {self.cpu.R[7]}")
            self.log(f"FLAGS: Z={self.cpu.Z}  C={self.cpu.C}  N={self.cpu.N}")
            self.log("════════════════════════════════════════")
            self.btn_step.configure(state="disabled")
            self.btn_run.configure(state="disabled")
            
    def do_run(self):
        if self.cpu.halted: return
        self.running = True
        self.btn_step.configure(state="disabled")
        self.btn_run.configure(text="PAUSE", command=self.do_pause)
        self.run_loop()
        
    def do_pause(self):
        self.running = False
        self.btn_run.configure(text="RUN", command=self.do_run)
        self.btn_step.configure(state="normal")
        
    def run_loop(self):
        if not self.running or self.cpu.halted:
            self.do_pause()
            return
        self.do_step()
        self.after(300, self.run_loop)
        
    def do_reset(self):
        self.cpu.reset()
        self.step_count = 0
        self.running = False
        self.do_pause()
        self.log_viewer.configure(state="normal")
        self.log_viewer.delete("1.0", "end")
        self.log_viewer.configure(state="disabled")
        self.btn_step.configure(state="disabled")
        self.btn_run.configure(state="disabled")
        self.update_ui()

if __name__ == "__main__":
    if hasattr(sys, '_MEIPASS'):
        pass
    app = SimulatorApp()
    app.mainloop()
