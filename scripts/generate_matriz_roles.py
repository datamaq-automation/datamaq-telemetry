"""Genera docs/matriz-roles-permisos.md leyendo las rutas FastAPI con AST (sin importar la app).

Para cada endpoint de src/infrastructure/fastapi/routes/ registra:
- los guards de rol que declara (Depends(requiere_rol_*), Depends(no_permitido_para_invitados_2fa)),
  con los roles que cada uno deja pasar, calculados evaluando la condición del propio guard;
- si la ruta solo exige autenticación (Depends(get_usuario_actual)) o no declara ninguna dependencia de auth;
- si el cuerpo de la ruta o de sus dependencias propias compara el rol a mano (ROLES_ACCESO_GLOBAL, "rol" o
  nombres de rol como literales).

Limitación: los chequeos de rol dentro de funciones auxiliares llamadas desde el cuerpo no se detectan.
Esa parte se verifica leyendo el código y queda listada como inconsistencia en la documentación.

Uso:
    python scripts/generate_matriz_roles.py           # escribe docs/matriz-roles-permisos.md
    python scripts/generate_matriz_roles.py --check   # falla si el archivo commiteado está desactualizado
"""

import ast
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
RUTAS_DIR = ROOT_DIR / "src" / "infrastructure" / "fastapi" / "routes"
FASTAPI_DIR = ROOT_DIR / "src" / "infrastructure" / "fastapi"
DEPENDENCIAS = FASTAPI_DIR / "dependencies.py"
ROLES_FUENTE = ROOT_DIR / "src" / "application" / "use_cases" / "autenticar_usuario.py"
SALIDA = ROOT_DIR / "docs" / "matriz-roles-permisos.md"

METODOS_HTTP = {"get", "post", "put", "patch", "delete"}
GUARDS_DE_ROL = {
    "requiere_rol_superadmin",
    "requiere_rol_auditor_o_superadmin",
    "requiere_rol_admin",
    "requiere_rol_escritura",
}
DEPENDENCIA_AUTH = "get_usuario_actual"
NOMBRES_DE_ROL_EN_CODIGO = {
    "superadmin",
    "admin",
    "operador",
    "mantenimiento",
    "ingeniero",
    "auditor",
}


def leer_roles_validos() -> list[str]:
    arbol = ast.parse(ROLES_FUENTE.read_text(encoding="utf-8"))
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "ROLES_VALIDOS" for t in nodo.targets
        ):
            return sorted(
                c.value for c in ast.walk(nodo.value) if isinstance(c, ast.Constant) and isinstance(c.value, str)
            )
    raise RuntimeError("No se encontró ROLES_VALIDOS en autenticar_usuario.py")


def roles_que_pasan(funcion: ast.FunctionDef, roles: list[str]) -> set[str]:
    """Evalúa las condiciones `if ... raise` del guard para cada rol. Pasa el rol si ninguna condición lo rechaza."""
    condiciones = [n.test for n in funcion.body if isinstance(n, ast.If)]
    permitidos: set[str] = set()
    for rol in roles:
        contexto = {"claims": {"rol": rol}}
        rechazado = any(eval(compile(ast.Expression(c), "<guard>", "eval"), {}, contexto) for c in condiciones)
        if not rechazado:
            permitidos.add(rol)
    return permitidos


def guards_de_rol(roles: list[str]) -> dict[str, set[str]]:
    arbol = ast.parse(DEPENDENCIAS.read_text(encoding="utf-8"))
    return {
        n.name: roles_que_pasan(n, roles)
        for n in arbol.body
        if isinstance(n, ast.FunctionDef) and n.name in GUARDS_DE_ROL
    }


def nombre_de_depends(nodo: ast.AST) -> str | None:
    """Devuelve el nombre de la dependencia en `Depends(nombre)` o None."""
    if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Name) and nodo.func.id == "Depends" and nodo.args:
        objetivo = nodo.args[0]
        if isinstance(objetivo, ast.Name):
            return objetivo.id
    return None


def alias_de_dependencias() -> dict[str, list[str]]:
    """Alias de tipo como `PlantaPermitida = Annotated[str, Depends(resolver_planta_permitida)]`.

    Se buscan en los módulos de la capa FastAPI; un parámetro tipado con el alias hereda sus dependencias.
    """
    alias: dict[str, list[str]] = {}
    for archivo in [*FASTAPI_DIR.glob("*.py"), *RUTAS_DIR.glob("*.py")]:
        for nodo in ast.parse(archivo.read_text(encoding="utf-8")).body:
            if isinstance(nodo, ast.Assign) and isinstance(nodo.value, ast.Subscript):
                nombres = [n for c in ast.walk(nodo.value) if (n := nombre_de_depends(c))]
                for objetivo in nodo.targets:
                    if isinstance(objetivo, ast.Name) and nombres:
                        alias[objetivo.id] = nombres
    return alias


def dependencias_de(funcion: ast.FunctionDef) -> list[str]:
    nombres: list[str] = []
    alias = alias_de_dependencias()
    for argumento in [*funcion.args.args, *funcion.args.kwonlyargs]:
        if argumento.annotation is not None:
            nombres += [n for n in map(nombre_de_depends, ast.walk(argumento.annotation)) if n]
            nombres += [
                d for c in ast.walk(argumento.annotation) if isinstance(c, ast.Name) for d in alias.get(c.id, [])
            ]
    for defecto in [*funcion.args.defaults, *funcion.args.kw_defaults]:
        if defecto is not None:
            nombres += [n for n in map(nombre_de_depends, ast.walk(defecto)) if n]
    return nombres


def hay_chequeo_manual(funcion: ast.FunctionDef) -> bool:
    for nodo in ast.walk(funcion):
        if isinstance(nodo, ast.Name) and nodo.id == "ROLES_ACCESO_GLOBAL":
            return True
        if isinstance(nodo, ast.Constant) and nodo.value in NOMBRES_DE_ROL_EN_CODIGO:
            return True
        if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute) and nodo.func.attr == "get":
            if nodo.args and isinstance(nodo.args[0], ast.Constant) and nodo.args[0].value == "rol":
                return True
    return False


def indice_de_funciones_auxiliares() -> dict[str, ast.FunctionDef]:
    """Funciones de nivel módulo en src/infrastructure/fastapi/*.py (para seguir dependencias propias)."""
    indice: dict[str, ast.FunctionDef] = {}
    for archivo in sorted(FASTAPI_DIR.glob("*.py")):
        for nodo in ast.parse(archivo.read_text(encoding="utf-8")).body:
            if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
                indice.setdefault(nodo.name, nodo)
    return indice


@dataclass
class Endpoint:
    metodo: str
    ruta: str
    archivo: str
    handler: str
    guards: list[str] = field(default_factory=list)
    autenticacion: str = ""
    chequeo_manual: bool = False
    roles: set[str] = field(default_factory=set)


def nombres_de_lista(valor: ast.AST) -> list[str]:
    """Nombres de `Depends(...)` dentro de una lista `dependencies=[...]`."""
    if isinstance(valor, ast.List):
        return [n for elemento in valor.elts if (n := nombre_de_depends(elemento))]
    return []


def config_del_router(arbol: ast.Module) -> tuple[str, list[str]]:
    """Prefijo y dependencias a nivel router, de `router = APIRouter(...)`."""
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "router" for t in nodo.targets):
            if isinstance(nodo.value, ast.Call):
                prefijo = ""
                deps: list[str] = []
                for kw in nodo.value.keywords:
                    if kw.arg == "prefix" and isinstance(kw.value, ast.Constant):
                        prefijo = str(kw.value.value)
                    if kw.arg == "dependencies":
                        deps = nombres_de_lista(kw.value)
                return prefijo, deps
    return "", []


def endpoints(roles: list[str]) -> list[Endpoint]:
    guards = guards_de_rol(roles)
    auxiliares = indice_de_funciones_auxiliares()
    resultado: list[Endpoint] = []
    for archivo in sorted(RUTAS_DIR.glob("*_router.py")):
        arbol = ast.parse(archivo.read_text(encoding="utf-8"))
        prefijo, deps_router = config_del_router(arbol)
        for funcion in [n for n in arbol.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
            for decorador in funcion.decorator_list:
                if not (
                    isinstance(decorador, ast.Call)
                    and isinstance(decorador.func, ast.Attribute)
                    and decorador.func.attr in METODOS_HTTP
                    and isinstance(decorador.func.value, ast.Name)
                    and decorador.func.value.id == "router"
                    and decorador.args
                    and isinstance(decorador.args[0], ast.Constant)
                ):
                    continue
                try:
                    ruta_relativa = archivo.relative_to(ROOT_DIR).as_posix()
                except ValueError:
                    ruta_relativa = archivo.name
                ep = Endpoint(
                    metodo=decorador.func.attr.upper(),
                    ruta=f"{prefijo}{decorador.args[0].value}",
                    archivo=ruta_relativa,
                    handler=funcion.name,
                )
                deps_decorador = [
                    n for kw in decorador.keywords if kw.arg == "dependencies" for n in nombres_de_lista(kw.value)
                ]
                nombres = [*deps_router, *deps_decorador]
                funciones = [funcion]
                visto: set[str] = set()
                permitidos: set[str] = set(roles)
                while funciones:
                    actual = funciones.pop()
                    ep.chequeo_manual = ep.chequeo_manual or hay_chequeo_manual(actual)
                    nombres += dependencias_de(actual)
                    while nombres:
                        nombre = nombres.pop()
                        if nombre in visto:
                            continue
                        visto.add(nombre)
                        if nombre in guards:
                            ep.guards.append(nombre)
                            permitidos &= guards[nombre]
                        elif nombre == DEPENDENCIA_AUTH:
                            ep.autenticacion = "autenticado (cualquier rol)"
                        elif nombre in auxiliares:
                            funciones.append(auxiliares[nombre])
                        # Otras dependencias son infraestructura (sesión de BD, configuración, casos de uso): no aportan rol.
                ep.roles = permitidos
                if not ep.autenticacion and not ep.guards:
                    ep.autenticacion = "sin dependencia de auth detectada"
                resultado.append(ep)
    return sorted(resultado, key=lambda e: (e.ruta, e.metodo))


def lista(valores) -> str:
    return ", ".join(f"`{v}`" for v in sorted(valores)) if valores else "—"


def generar() -> str:
    roles = leer_roles_validos()
    eps = endpoints(roles)
    lineas = [
        "<!-- Generado por scripts/generate_matriz_roles.py. No editar a mano: regenerar. -->",
        "# Matriz de roles y permisos (generada desde el código)",
        "",
        f"Endpoints analizados: **{len(eps)}**. Roles válidos (`ROLES_VALIDOS`): {lista(roles)}.",
        "",
        'Cómo se lee: "Roles que pasan" es lo que deja el guard de rol que la ruta declara (evaluado con la condición '
        'real del guard). Si la columna "Chequeo manual" dice `sí`, el cuerpo de la ruta o de una dependencia propia '
        "compara el rol o usa `ROLES_ACCESO_GLOBAL`: ese recorte no está en la columna y hay que leer la ruta para saberlo.",
        "",
        'Con `AUTH_REQUIRED` apagado, `get_usuario_actual` devuelve `{"sub": "anon", "rol": "admin"}`: '
        "todos los guards dejan pasar y la matriz no aplica. Es un comportamiento de desarrollo.",
        "",
        "## Resumen por guard",
        "",
        "| Guard | Roles que pasan |",
        "|---|---|",
    ]
    for nombre, permitidos in sorted(guards_de_rol(roles).items()):
        lineas.append(f"| `{nombre}` | {lista(permitidos)} |")
    lineas += [
        "",
        "## Endpoints",
        "",
        "| Método | Ruta | Guards | Roles que pasan | Autenticación | Chequeo manual | Código |",
        "|---|---|---|---|---|---|---|",
    ]
    for ep in eps:
        lineas.append(
            f"| {ep.metodo} | `{ep.ruta}` | {lista(ep.guards)} | {lista(ep.roles) if ep.guards else 'todos (sin guard)'} "
            f"| {ep.autenticacion or '—'} | {'sí' if ep.chequeo_manual else 'no'} | `{ep.archivo}:{ep.handler}` |"
        )
    return "\n".join(lineas) + "\n"


def main(argumentos: list[str]) -> int:
    contenido = generar()
    if "--check" in argumentos:
        actual = SALIDA.read_text(encoding="utf-8") if SALIDA.exists() else ""
        if actual != contenido:
            print(f"{SALIDA} está desactualizado: ejecutar scripts/generate_matriz_roles.py")
            return 1
        print(f"{SALIDA} sincronizado")
        return 0
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(contenido, encoding="utf-8")
    print(f"Escrito {SALIDA}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
