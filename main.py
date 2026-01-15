import socket
import time
import argparse
import sys
from cb_parser import parse_file

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
        return self.tn.recv(4096).decode('ascii')

    def set_extest(self):
        print(f"[*] Trecem în modul EXTEST...")
        # 0x26 este codul opcode pentru EXTEST la Xilinx Artix-7
        self.send_cmd(f"irscan {TAP_NAME} 0x26")

    def write_dr(self, bit_string):
        # bit_string trebuie să fie lungimea registrului BSR (ex: 989)
        # Atenție: JTAG trimite LSB first, verifică ordinea în funcție de bsdl
        self.send_cmd(f"drscan {TAP_NAME} {len(bit_string)} {bit_string}")


def perform_toggle(controller, bsdl, target_cells, duration=0.5):
    # Resetăm tot registrul la '0' (safe state)
    boundary_len = 989  # Valoarea din BSDL-ul tău

    for cell_info in target_cells:
        port = cell_info['port']
        data_idx = cell_info['data_idx']
        ctrl_idx = cell_info['ctrl_idx']

        print(f"[*] Toggle pe pinul: {port} (Data cell: {data_idx}, Control cell: {ctrl_idx})")

        # Pas 1: Aprindem (Control=1, Data=1) -> presupunem active-high control
        bits = ["0"] * boundary_len
        if ctrl_idx is not None: bits[ctrl_idx] = "1"
        bits[data_idx] = "1"
        controller.write_dr("".join(bits[::-1]))  # JTAG trimite invers de obicei
        time.sleep(duration)

        # Pas 2: Stingem (Control=1, Data=0)
        bits[data_idx] = "0"
        controller.write_dr("".join(bits[::-1]))
        time.sleep(duration)


def main():
    parser = argparse.ArgumentParser(description='JTAG Boundary Scan Tool pentru Xilinx')
    parser.add_argument('--pin', type=str, help='Numele pinului din BSDL (ex: IO_U8)')
    parser.add_argument('--all', action='store_true', help='Toggle secvențial pe toți pinii de output')
    args = parser.parse_args()

    # 1. Parsare BSDL
    print(f"[*] Se încarcă fișierul: {BSDL_FILE}...")
    bsdl_obj = parse_file(BSDL_FILE)
    cells = bsdl_obj.boundary_register.cells

    # 2. Identificare celule de output
    # Xilinx BSDL include ccell (control cell) în descriere.
    # Trebuie să extragem manual ccell din textul celulei dacă parserul nu o face direct.
    # Pentru acest exemplu simplificat, vom căuta manual în listă:

    output_map = []
    for c in cells:
        if c.port_name and "output" in c.function:
            # În BSDL-ul tău, celula de control este de obicei cell_number - 1 sau specificată
            # Vom încerca să deducem celula de control (ccell)
            output_map.append({
                'port': c.port_name,
                'data_idx': c.cell_number,
                'ctrl_idx': c.cell_number - 1  # Mapare empirică pt Xilinx Artix
            })
    print(output_map)
    # 3. Execuție
    jtag = JTAGController(HOST, PORT)
    jtag.set_extest()

    if args.pin:
        target = [item for item in output_map if item['port'] == args.pin.upper()]
        if not target:
            print(f"EROARE: Pinul {args.pin} nu a fost găsit ca fiind de OUTPUT.")
            return
        perform_toggle(jtag, bsdl_obj, target)

    elif args.all:
        print(f"[*] Începem toggle secvențial pentru {len(output_map)} pini...")
        perform_toggle(jtag, bsdl_obj, output_map, duration=0.1)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()