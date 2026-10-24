"""scripts/inventario_patrones_creacionales.py — Inventario de clases y señales de patrones creacionales en src/.

Análisis estático con AST. Es una heurística: marca dónde aparecen las estructuras típicas,
pero no puede saber la intención del autor. Revisar cada hallazgo a mano.

Señales que busca:
  - Singleton: instancia creada a nivel de módulo (X = Clase(...)), método __new__ o caché @lru_cache.
  - Factory Method: función o método con prefijo create_/crear_/make_/build_/fabricar_/nuevo_ que devuelve algo.
  - Abstract Factory: una interfaz (ABC o Protocol) con dos o más métodos de fábrica.
  - Builder: clase con nombre *Builder, o con dos o más métodos públicos que terminan en `return self`
    (interfaz fluida). Las funciones construir_* no cuentan: son fábricas de funciones, no builders.
  - Prototype: método de clonación por nombre (clone, clonar, copiar, duplicar, prototype) o llamada a
    copy.deepcopy, copy.copy, model_copy o dataclasses.replace dentro de una función.

Límites conocidos: no sigue imports, así que `replace(...)` importado directamente desde dataclasses
no se detecta; solo cuenta `dataclasses.replace(...)`.

Uso:
  python scripts/inventario_patrones_creacionales.py
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SRC = RAIZ / "src"
PREFIJOS_FABRICA = re.compile(r"^(create|crear|make|build|fabricar|nuevo)_")
NOMBRES_CLONACION = {"clone", "clonar", "copy", "copiar", "duplicar", "prototype"}
FUNCION = (ast.FunctionDef, ast.AsyncFunctionDef)


@dataclass
class Hallazgo:
    archivo: str
    linea: int
    descripcion: str


@dataclass
class Inventario:
    clases: list[tuple[str, str, int, bool]] = field(default_factory=list)  # nombre, archivo, línea, es_interfaz
    singletons: list[Hallazgo] = field(default_factory=list)
    fabricas: list[Hallazgo] = field(default_factory=list)
    abstract_factory: list[Hallazgo] = field(default_factory=list)
    builders: list[Hallazgo] = field(default_factory=list)
    prototipos: list[Hallazgo] = field(default_factory=list)


def _nombre(nodo: ast.expr) -> str:
    if isinstance(nodo, ast.Name):
        return nodo.id
    if isinstance(nodo, ast.Attribute):
        return nodo.attr
    if isinstance(nodo, ast.Subscript):
        return _nombre(nodo.value)
    return ""


def _es_interfaz(clase: ast.ClassDef) -> bool:
    return any(_nombre(base) in {"ABC", "Protocol"} for base in clase.bases)


def _usa_lru_cache(funcion: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for decorador in funcion.decorator_list:
        destino = decorador.func if isinstance(decorador, ast.Call) else decorador
        if _nombre(destino) in {"lru_cache", "cache"}:
            return True
    return False


def _termina_en_return_self(funcion: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    if not funcion.body:
        return False
    ultimo = funcion.body[-1]
    return isinstance(ultimo, ast.Return) and isinstance(ultimo.value, ast.Name) and ultimo.value.id == "self"


def _es_llamada_de_clonacion(llamada: ast.Call) -> bool:
    """copy.deepcopy(...), copy.copy(...), x.model_copy(...) o dataclasses.replace(...)."""
    destino = llamada.func
    if not isinstance(destino, ast.Attribute):
        return False
    origen = destino.value.id if isinstance(destino.value, ast.Name) else ""
    if origen == "copy" and destino.attr in {"deepcopy", "copy"}:
        return True
    if destino.attr == "model_copy":
        return True
    return origen == "dataclasses" and destino.attr == "replace"


def _instancias_de_modulo(arbol: ast.Module, nombres_clases: set[str]) -> list[tuple[str, int, str]]:
    """Asignaciones a nivel de módulo cuyo valor es una llamada a una clase del proyecto."""
    encontradas: list[tuple[str, int, str]] = []
    for nodo in arbol.body:
        if isinstance(nodo, ast.Assign):
            valor, objetivos = nodo.value, nodo.targets
        elif isinstance(nodo, ast.AnnAssign) and nodo.value is not None:
            valor, objetivos = nodo.value, [nodo.target]
        else:
            continue
        if isinstance(valor, ast.Call) and _nombre(valor.func) in nombres_clases:
            for objetivo in objetivos:
                if isinstance(objetivo, ast.Name):
                    encontradas.append((objetivo.id, nodo.lineno, _nombre(valor.func)))
    return encontradas


def _analizar_clase(nodo: ast.ClassDef, archivo: str, inv: Inventario) -> None:
    metodos = [m for m in nodo.body if isinstance(m, FUNCION)]
    inv.clases.append((nodo.name, archivo, nodo.lineno, _es_interfaz(nodo)))
    if any(m.name == "__new__" for m in metodos):
        inv.singletons.append(Hallazgo(archivo, nodo.lineno, f"{nodo.name}.__new__ (control de instancia)"))
    fabricas = [m.name for m in metodos if PREFIJOS_FABRICA.match(m.name)]
    if len(fabricas) >= 2 and _es_interfaz(nodo):
        inv.abstract_factory.append(Hallazgo(archivo, nodo.lineno, f"{nodo.name}: {', '.join(fabricas)}"))

    fluidos = [m.name for m in metodos if not m.name.startswith("_") and _termina_en_return_self(m)]
    if nodo.name.endswith("Builder"):
        inv.builders.append(Hallazgo(archivo, nodo.lineno, f"{nodo.name} (nombre de builder)"))
    elif len(fluidos) >= 2:
        inv.builders.append(Hallazgo(archivo, nodo.lineno, f"{nodo.name}: interfaz fluida ({', '.join(fluidos)})"))

    clonadores = [m.name for m in metodos if m.name.lower() in NOMBRES_CLONACION]
    for nombre in clonadores:
        inv.prototipos.append(Hallazgo(archivo, nodo.lineno, f"{nodo.name}.{nombre}() (método de clonación)"))


def _clonaciones_en_funciones(arbol: ast.Module, archivo: str, inv: Inventario) -> None:
    vistos: set[int] = set()
    for funcion in ast.walk(arbol):
        if not isinstance(funcion, FUNCION):
            continue
        for llamada in ast.walk(funcion):
            if isinstance(llamada, ast.Call) and _es_llamada_de_clonacion(llamada) and llamada.lineno not in vistos:
                vistos.add(llamada.lineno)
                inv.prototipos.append(Hallazgo(archivo, llamada.lineno, f"clonación dentro de {funcion.name}()"))


def analizar_archivo(ruta: Path, inv: Inventario, nombres_clases: set[str]) -> None:
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    archivo = ruta.relative_to(RAIZ).as_posix()

    for nombre, linea, clase in _instancias_de_modulo(arbol, nombres_clases):
        inv.singletons.append(Hallazgo(archivo, linea, f"{nombre} = {clase}(...) a nivel de módulo"))

    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.ClassDef):
            _analizar_clase(nodo, archivo, inv)
        if isinstance(nodo, FUNCION):
            if _usa_lru_cache(nodo):
                inv.singletons.append(
                    Hallazgo(archivo, nodo.lineno, f"{nodo.name}: @lru_cache (una instancia por argumentos)")
                )
            if PREFIJOS_FABRICA.match(nodo.name) and nodo.returns is not None:
                inv.fabricas.append(Hallazgo(archivo, nodo.lineno, f"{nodo.name}()"))

    _clonaciones_en_funciones(arbol, archivo, inv)


def inventariar() -> Inventario:
    archivos = sorted(p for p in SRC.rglob("*.py") if "__pycache__" not in p.parts)
    arboles = {p: ast.parse(p.read_text(encoding="utf-8")) for p in archivos}
    nombres_clases = {n.name for arbol in arboles.values() for n in ast.walk(arbol) if isinstance(n, ast.ClassDef)}

    inv = Inventario()
    for ruta in archivos:
        analizar_archivo(ruta, inv, nombres_clases)
    return inv


def _imprimir_seccion(titulo: str, hallazgos: list[Hallazgo]) -> None:
    print(f"\n{titulo} ({len(hallazgos)})")
    for h in sorted(hallazgos, key=lambda x: (x.archivo, x.linea)):
        print(f"  {h.archivo}:{h.linea}  {h.descripcion}")


def main() -> None:
    inv = inventariar()
    interfaces = sum(1 for _, _, _, es in inv.clases if es)
    print(
        f"Clases en src/: {len(inv.clases)}  (interfaces ABC/Protocol: {interfaces}, concretas: {len(inv.clases) - interfaces})"
    )
    _imprimir_seccion("Singleton", inv.singletons)
    _imprimir_seccion("Factory Method (funciones de fábrica con tipo de retorno)", inv.fabricas)
    _imprimir_seccion("Abstract Factory (interfaz ABC/Protocol con 2 o más métodos de fábrica)", inv.abstract_factory)
    _imprimir_seccion("Builder", inv.builders)
    _imprimir_seccion("Prototype", inv.prototipos)
    print(
        "\nNota: singleton de módulo significa solo 'instancia única al importar'. Puede ser intencional o un "
        "efecto secundario; revisar cada caso."
    )


if __name__ == "__main__":
    main()
