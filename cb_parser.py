import re


class BSDLCell:
    def __init__(self, num, port, func):
        self.cell_number = int(num)
        # Curățăm numele portului de ghilimele și spații
        self.port_name = port.strip().replace('"', '') if port.strip() != "*" else None
        self.function = func.strip()


class BSDLObject:
    def __init__(self, cells):
        class Reg: pass

        self.boundary_register = Reg()
        self.boundary_register.cells = cells


def parse_file(filename):
    with open(filename, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    # Debug: vedem cât de mare e fișierul
    print(f"--- Debug: Citire fișier {filename} ({len(content)} caractere) ---")

    # Căutăm "BOUNDARY_REGISTER" urmat de orice până la "is"
    # Folosim re.DOTALL pentru ca .* să prindă și linii noi
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

    # Regex pentru celule: Cifră urmată de paranteză, apoi extragem ID, Port și Funcție
    # Ex: 52 (BC_2, IO_U8, output3, X, 51, 1, Z)
    cell_pattern = re.compile(r'(\d+)\s*\(\s*[\w\d_]+\s*,\s*([\w\d_*"]+)\s*,\s*([\w\d_]+)')

    matches = cell_pattern.findall(block)
    cells = [BSDLCell(m[0], m[1], m[2]) for m in matches]

    print(f"Succes: Am extras {len(cells)} celule.")

    if not cells:
        # Debug în caz de eșec: printăm primele 100 de caractere din blocul găsit
        print(f"Blocul detectat începe cu: {block[:100]}")
        raise RuntimeError("Eroare: Secțiunea a fost găsită, dar pattern-ul celulelor nu se potrivește.")

    return BSDLObject(cells)