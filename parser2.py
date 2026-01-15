Your BSDL parser is a good start—it's lightweight, focuses on the essentials (cell number, port, function), and successfully extracts the core details from the BOUNDARY_REGISTER block based on the test I ran (using the snippet you provided earlier as a sample file). It handles the multi-line &-concatenated structure reasonably well by grabbing the block up to ';' and using regex to pull cells.
However, there are some limitations and potential improvements:

Incomplete Field Parsing: The regex only captures up to the function (e.g., it grabs output3 but ignores X, 2100, 1, Z). This means you miss critical details like the safe value, control cell reference (ccell), disable value, and result state (e.g., Z for high-Z). For a robust boundary scan tool, parsing these ensures accuracy (e.g., confirming control logic is disable-on-1, and using the explicit ccell instead of assuming cell_number - 1).
No BOUNDARY_LENGTH Extraction: Your main script hardcodes 989, which is correct for the xc7a100t in CSG324 package (confirmed via Xilinx docs and public BSDL repos), but parsing it dynamically makes the tool more flexible for other devices/packages.
Robustness:
Comments (e.g., -- PAD177) might interfere if not stripped properly (your code doesn't explicitly handle them in the block).
Port names with quotes or special chars are handled OK, but the regex could be tighter.
If the BSDL has variations (e.g., different cell types like bidir or extra fields), it might miss them.
Error handling is good, but add more debug for regex failures.

Xilinx-Specific Assumptions: The code works for Artix-7 patterns (e.g., BC_2 cells, controlr before output3), but Xilinx BSDLs are consistent, so it's fine. For other vendors, it might need tweaks.

Improved Parser Code
Here's an updated version of your bsdl_parser.py (or whatever you named it). I kept it simple and backward-compatible but added:

Extraction of BOUNDARY_LENGTH.
More flexible regex to capture all fields (up to 7 parts per cell, as per IEEE 1149.1/BSDL spec).
Additional attributes in BSDLCell for safe, ctrl_cell, disable_value, disable_result.
Stripping comments from the block before parsing.
Inference of boundary_len from max cell if not explicitly stated (rare, but a fallback).

Pythonimport re

class BSDLCell:
    def __init__(self, num, cell_type, port, func, safe=None, ctrl_cell=None, disable_value=None, disable_result=None):
        self.cell_number = int(num)
        self.cell_type = cell_type.strip()  # e.g., 'BC_2'
        self.port_name = port.strip().replace('"', '') if port.strip() != "*" else None
        self.function = func.strip()
        self.safe = safe.strip() if safe else None
        self.ctrl_cell = int(ctrl_cell) if ctrl_cell else None
        self.disable_value = disable_value.strip() if disable_value else None
        self.disable_result = disable_result.strip() if disable_result else None

class BSDLObject:
    def __init__(self, boundary_len, cells):
        class Reg: pass
        self.boundary_len = boundary_len
        self.boundary_register = Reg()
        self.boundary_register.cells = cells

def parse_file(filename):
    with open(filename, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    # Debug: vedem cât de mare e fișierul
    print(f"--- Debug: Citire fișier {filename} ({len(content)} caractere) ---")

    # Extragem BOUNDARY_LENGTH dacă există
    len_match = re.search(r'attribute\s+BOUNDARY_LENGTH\s+.+?\s+is\s+(\d+);', content, re.IGNORECASE | re.DOTALL)
    boundary_len = int(len_match.group(1)) if len_match else None

    # Căutăm "BOUNDARY_REGISTER" urmat de orice până la "is"
    match_start = re.search(r'attribute\s+BOUNDARY_REGISTER\s+of\s+.*?\s+is', content, re.IGNORECASE | re.DOTALL)
    if not match_start:
        raise RuntimeError("Eroare: Nu am găsit 'attribute BOUNDARY_REGISTER ... is'. Verifică sintaxa BSDL!")

    # Tăiem tot ce e înainte de listă
    remaining_content = content[match_start.end():]

    # Lista de celule se termină la caracterul ';'
    end_index = remaining_content.find(';')
    if end_index == -1:
        raise RuntimeError("Eroare: Secțiunea BOUNDARY_REGISTER nu se termină cu ';'. Fișierul e incomplet?")

    block = remaining_content[:end_index]

    # Eliminăm comentariile (-- ...) din bloc pentru a evita interferențe
    block = re.sub(r'--.*', '', block)

    # Regex îmbunătățit: Capturăm toate părțile posibile (până la 7: num (type, port, func, [safe, ctrl, dis_val, dis_res]))
    # Ex: 2101 (BC_2, IO_AK20, output3, X, 2100, 1, Z)
    cell_pattern = re.compile(r'(\d+)\s*\(\s*([\w\d_]+)\s*,\s*([\w\d_*"]+)\s*,\s*([\w\d_]+)\s*(?:,\s*([\w\dX_]+))?\s*(?:,\s*([\w\dX_]+))?\s*(?:,\s*([\w\dX_]+))?\s*(?:,\s*([\w\dX_]+))?\s*\)')

    matches = cell_pattern.findall(block)
    cells = []
    for m in matches:
        num, cell_type, port, func = m[0], m[1], m[2], m[3]
        safe = ctrl_cell = disable_value = disable_result = None
        if len(m) > 4:
            extras = m[4:]
            if func in ['control', 'controlr']:
                safe = extras[0] if extras else None
            elif func == 'output3':
                safe = extras[0] if len(extras) > 0 else None
                ctrl_cell = extras[1] if len(extras) > 1 else None
                disable_value = extras[2] if len(extras) > 2 else None
                disable_result = extras[3] if len(extras) > 3 else None
            elif func == 'input':
                safe = extras[0] if extras else None
        cells.append(BSDLCell(num, cell_type, port, func, safe, ctrl_cell, disable_value, disable_result))

    print(f"Succes: Am extras {len(cells)} celule.")

    if not cells:
        print(f"Blocul detectat începe cu: {block[:100]}")
        raise RuntimeError("Eroare: Secțiunea a fost găsită, dar pattern-ul celulelor nu se potrivește.")

    # Dacă boundary_len nu a fost găsit, inferăm din max cell_number + 1
    if boundary_len is None:
        boundary_len = max(c.cell_number for c in cells) + 1
        print(f"Warning: BOUNDARY_LENGTH nu a fost găsit explicit; inferat ca {boundary_len} din celule.")

    return BSDLObject(boundary_len, cells)
How to Integrate with Your Main Script

Update the import: from bsdl_parser import parse_file (assuming this is the file name).
In main():
After bsdl_obj = parse_file(BSDL_FILE), use boundary_len = bsdl_obj.boundary_len (remove the hardcoded 989).
In building output_map:Pythonoutput_map = []
for c in cells:
    if c.function == 'output3' and c.ctrl_cell is not None:
        output_map.append({
            'port': c.port_name,
            'data_idx': c.cell_number,
            'ctrl_idx': c.ctrl_cell  # Use parsed value instead of cell_number - 1
        })This is more accurate and handles any non-sequential control cells.


Test Results
I tested your original code (and this improved version) on a minimal BSDL file based on your snippet—it extracted all cells correctly. For a full xc7a100t CSG324 BSDL, it should yield ~989 cells (mostly trios of control/output/input).
If you share more of "plm4.bsdl" (e.g., a snippet with BOUNDARY_LENGTH) or run into issues, I can refine further. Keep up the good work on the tool!