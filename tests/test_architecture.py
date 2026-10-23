import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICES = ROOT / "services"
MAX_LINES = 500

ALLOWED_IMPORTS = {
    "domain": set(),
    "application": {"domain"},
    "infrastructure": {"domain", "application"},
    "presentation": {"domain", "application", "infrastructure"},
}
LAYERS = set(ALLOWED_IMPORTS)


def python_files():
    """Lista todos los archivos .py del repositorio fuera del entorno virtual."""
    return [
        p for p in ROOT.rglob("*.py") if ".venv" not in p.parts and "node_modules" not in p.parts
    ]


def layer_of(path: Path):
    """Devuelve la capa de un archivo dentro de un servicio, o None si no pertenece a una."""
    parts = path.relative_to(ROOT).parts
    if len(parts) < 5 or parts[0] != "services" or parts[2] != "src":
        return None
    return parts[4] if parts[4] in LAYERS else None


def imported_layers(path: Path, package: str):
    """Devuelve las capas del mismo servicio que importa un archivo."""
    found = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        names = []
        if isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        elif isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        for name in names:
            segments = name.split(".")
            if segments[0] == package and len(segments) > 1 and segments[1] in LAYERS:
                found.add(segments[1])
    return found


def test_no_file_exceeds_line_limit():
    offenders = {
        str(p.relative_to(ROOT)): n
        for p in python_files()
        if (n := len(p.read_text(encoding="utf-8").splitlines())) > MAX_LINES
    }
    assert not offenders, f"Archivos con mas de {MAX_LINES} lineas: {offenders}"


def test_layers_only_depend_inward():
    violations = []
    for path in python_files():
        layer = layer_of(path)
        if layer is None:
            continue
        package = path.relative_to(ROOT).parts[3]
        for imported in imported_layers(path, package):
            if imported != layer and imported not in ALLOWED_IMPORTS[layer]:
                violations.append(f"{path.relative_to(ROOT)}: {layer} -> {imported}")
    assert not violations, "Dependencias invalidas entre capas:\n" + "\n".join(violations)
