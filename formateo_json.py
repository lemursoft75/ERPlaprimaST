import json
from pathlib import Path

def escape_private_key_from_file(relative_path):
    file_path = Path(__file__).parent / relative_path
    with file_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    # Escapa las líneas del private_key
    if "private_key" in data:
        data["private_key"] = data["private_key"].replace("\n", "\\n")
    else:
        print("No se encontró el campo 'private_key' en el JSON.")
        return

    # Imprime el resultado formateado para pegar en secrets.toml
    print(json.dumps(data, indent=2))

# Usar ruta relativa
escape_private_key_from_file("utils/serviceAccountKey.json")