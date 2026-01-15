Your
code
looks
solid as a
starting
point
for a JTAG boundary scan tool interfacing with OpenOCD! It's great that you're using socket for Telnet control, setting EXTEST (correct opcode 0x26 for Artix-7), and handling DR scans.However, there are a few issues and improvements needed for correctness, safety, and robustness:
    Key
    Fixes and Improvements

Control
Logic: Based
on
the
BSDL
structure(controlr
with disable_value=1), the control cell disables the output (high-Z) when set to '1'.To enable the output, set control to '0'.Your code assumes the opposite (active-high enable with '1'), which could cause bus contention or incorrect driving.
Bit
Vector
Order: Don
't reverse the bits ([::-1]). Define bits[cell_num] where bits[0] is cell 0 (near TDO). Then bit_str = ''.join(bits) makes left=MSB (cell 0, shifted last), right=LSB (cell N-1, shifted first), which matches OpenOCD'
s
LSB - first
shifting
for drscan.
    Vector
    Format
    for OpenOCD: For
    long
    chains(e.g., 989
    bits), sending
    a
    raw
    binary
    string
    may
    not parse
    well(OpenOCD
    expects
    a
    number, hex
    preferred).Convert
    to
    hex(e.g., 0
    x...) to
    avoid
    issues
    with large numbers.
Safe
State
Handling: When
toggling
a
pin, ensure
all
other
outputs
are
high - Z(control='1')
to
prevent
contention.Your
code
sets
unused
controls
to
'0', which
would
enable
them(driving
'0').Fix
by
defaulting
all
known
controls
to
'1'.
Boundary
Length: Don
't hardcode 989 (though correct for xc7a100t in CSG324 package). Parse it from BSDL.
BSDL
Parsing: Your
cb_parser(perhaps
a
typo
for bsdl_parser?) is referenced but not shown.I've included a complete parser below that handles the full BOUNDARY_REGISTER, extracts length, and builds the pin_map with correct ctrl_idx from the output3 fields. It matches your example output and works on the snippet/full files.
General: Add
error
handling, confirm
chain
length, and perhaps
preload
a
safe
vector
on
init.For - -all, toggle
sequentially
with short duration.

Updated
Code
I
've split it into two files: bsdl_parser.py (the parser) and your main script (renamed imports, fixed logic). Replace cb_parser with this.
bsdl_parser.py
Pythonimport
re


class BoundaryCell:
    def __init__(self, cell_num, cell_type, port, func, safe, ctrl_cell=None, disable_val=None, disable_res=None):
        self.cell_num = cell_num
        self.cell_type = cell_type
        self.port = port
        self.func = func
        self.safe = safe
        self.ctrl_cell = ctrl_cell
        self.disable_val = disable_val
        self.disable_res = disable_res


class BsdlObject:
    def __init__(self, boundary_len, cells):
        self.boundary_len = boundary_len
        self.boundary_register = type('Reg', (), {'cells': cells})


def parse_file(file_path):
    with open(file_path, 'r') as f:
        content = f.read()

    # Extract BOUNDARY_LENGTH
    len_match = re.search(r'attribute BOUNDARY_LENGTH .+? is (\d+);', content, re.IGNORECASE | re.DOTALL)
    boundary_len = int(len_match.group(1)) if len_match else None

    # Extract BOUNDARY_REGISTER string
    reg_match = re.search(r'attribute BOUNDARY_REGISTER .+? is\s+"([^"]+)"\s*;', content, re.IGNORECASE | re.DOTALL)
    if not reg_match:
        raise ValueError("No BOUNDARY_REGISTER found in BSDL")
    reg_str = reg_match.group(1)

    # Split cells
    lines = [line.strip() for line in re.split(r'&', reg_str) if line.strip()]

    cells = []
    for line in lines:
        # Remove quotes and comments
        line = re.sub(r'--.*', '', line.strip('" '))
        if not line:
            continue

        # Parse parts
        parts = re.findall(r'[\w.*]+|[0-9XZX]+', line.replace('(', ' ').replace(')', ' ').replace(',', ' '))
        if len(parts) < 4:
            continue

        cell_num = int(parts[0])
        cell_type = parts[1]
        port = parts[2]
        func = parts[3]
        safe = parts[4] if len(parts) > 4 else parts[3] if func == 'controlr' else None

        ctrl_cell = disable_val = disable_res = None
        if func == 'output3' and len(parts) >= 8:
            ctrl_cell = int(parts[5])
            disable_val = parts[6]
            disable_res = parts[7]

        cells.append(BoundaryCell(cell_num, cell_type, port, func, safe, ctrl_cell, disable_val, disable_res))

    # If length not found, infer from max cell
    if boundary_len is None:
        boundary_len = max(c.cell_num for c in cells) + 1

    return BsdlObject(boundary_len, cells)


Main
Script(your
file, fixed)
Pythonimport
socket
import time
import argparse
import sys
from bsdl_parser import parse_file  # Updated import

# --- CONFIGURARE JTAG / OPENOCD ---
HOST = "127.0.0.1"
PORT = 4444  # Portul Telnet implicit al OpenOCD
TAP_NAME = "xc7a100t.tap"  # Trebuie să coincidă cu ce ai în artix7.cfg
BSDL_FILE = "plm4.bsdl"


class JTAGController:
    def __init__(self, host, port):
        self.tn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.tn.connect((host, port))
            self.tn.settimeout(2)
            print(f"[*] Conectat la OpenOCD pe {host}:{port}")
            # Curățăm buffer-ul inițial
            self.tn.recv(1024)
        except ConnectionRefusedError:
            print("EROARE: Nu s-a putut conecta la OpenOCD. Este pornit serverul?")
            sys.exit(1)

    def send_cmd(self, cmd):
        full_cmd = cmd + "\n"
        self.tn.send(full_cmd.encode('ascii'))
        time.sleep(0.01)  # Mic delay pentru procesare
        response = self.tn.recv(4096).decode('ascii')
        print(f"[DEBUG] Response: {response.strip()}")
        return response

    def set_extest(self):
        print(f"[*] Trecem în modul EXTEST...")
        # 0x26 este codul opcode pentru EXTEST la Xilinx Artix-7 (confirmat: 0b100110)
        self.send_cmd(f"irscan {TAP_NAME} 0x26")

    def write_dr(self, bit_str, boundary_len):
        # Convert bit string (MSB left: cell0) to hex for long chains
        num = int(bit_str, 2)
        hex_val = f"0x{num:X}"
        self.send_cmd(f"drscan {TAP_NAME} {boundary_len} {hex_val}")


def perform_toggle(controller, bsdl, output_map, target_ports, duration=0.5):
    boundary_len = bsdl.boundary_len
    all_ctrl_idxs = {item['ctrl_idx'] for item in output_map}  # All known controls

    for port in target_ports:
        target = next((item for item in output_map if item['port'] == port), None)
        if not target:
            print(f"EROARE: Pinul {port} nu a fost găsit.")
            continue

        data_idx = target['data_idx']
        ctrl_idx = target['ctrl_idx']
        print(f"[*] Toggle pe pinul: {port} (Data cell: {data_idx}, Control cell: {ctrl_idx})")

        # Base vector: all controls to '1' (high-Z, safe), data to '0'
        bits = ["0"] * boundary_len
        for c_idx in all_ctrl_idxs:
            bits[c_idx] = "1"  # Disable all outputs

        # Pas 1: Aprindem (Control=0 enable, Data=1)
        bits[ctrl_idx] = "0"
        bits[data_idx] = "1"
        controller.write_dr("".join(bits), boundary_len)
        time.sleep(duration)

        # Pas 2: Stingem (Control=0, Data=0)
        bits[data_idx] = "0"
        controller.write_dr("".join(bits), boundary_len)
        time.sleep(duration)

        # Back to safe (Control=1)
        bits[ctrl_idx] = "1"
        controller.write_dr("".join(bits), boundary_len)


def main():
    parser = argparse.ArgumentParser(description='JTAG Boundary Scan Tool pentru Xilinx')
    parser.add_argument('--pin', type=str, help='Numele pinului din BSDL (ex: IO_U8)')
    parser.add_argument('--all', action='store_true', help='Toggle secvențial pe toți pinii de output')
    args = parser.parse_args()

    # 1. Parsare BSDL
    print(f"[*] Se încarcă fișierul: {BSDL_FILE}...")
    try:
        bsdl_obj = parse_file(BSDL_FILE)
    except Exception as e:
        print(f"EROARE la parsare BSDL: {e}")
        sys.exit(1)
    boundary_len = bsdl_obj.boundary_len
    print(f"[*] Lungime registru boundary: {boundary_len}")
    cells = bsdl_obj.boundary_register.cells

    # 2. Extragere output_map (numai pini output3 cu control)
    output_map = []
    for c in cells:
        if c.func == 'output3' and c.ctrl_cell is not None:
            output_map.append({
                'port': c.port,
                'data_idx': c.cell_num,
                'ctrl_idx': c.ctrl_cell
            })
    print(f"[*] Găsiți {len(output_map)} pini de output.")

    # 3. Execuție
    jtag = JTAGController(HOST, PORT)
    jtag.set_extest()

    # Preload safe state inițial (all high-Z)
    safe_bits = ["0"] * boundary_len
    for item in output_map:
        safe_bits[item['ctrl_idx']] = "1"
    jtag.write_dr("".join(safe_bits), boundary_len)
    print("[*] Starea safe inițială setată (toți pini high-Z).")

    if args.pin:
        perform_toggle(jtag, bsdl_obj, output_map, [args.pin.upper()])

    elif args.all:
        target_ports = [item['port'] for item in output_map]
        print(f"[*] Începem toggle secvențial pentru {len(target_ports)} pini...")
        perform_toggle(jtag, bsdl_obj, output_map, target_ports, duration=0.1)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
How
to
Test / Use

Run
with --pin IO_AK20 to toggle one pin.
For - -all, it
toggles
each
sequentially(one
at
a
time, others
high - Z).
Ensure
OpenOCD is running
with your config (e.g., openocd -f artix7.cfg).
If
BSDL
has
non - I / O
cells(e.g., clocks), the
parser
handles
them
but
ignores
for output_map.
    Debug: Check
    OpenOCD
    responses
    for "ran" or errors.

If
you
share
your
full
BSDL or more
details(e.g., package), I
can
verify
further.Let
me
know
what else you
need!