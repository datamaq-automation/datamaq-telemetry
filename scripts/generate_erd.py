import argparse
import os
import sys

# Add project root to python path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# `models_cargas` se importa aunque no se use por nombre: registra las tablas del
# contexto de cargas en `Base.metadata`. Mismo motivo que en `alembic/env.py`.
from src.infrastructure.sqlalchemy import models_cargas  # noqa: E402,F401
from src.infrastructure.sqlalchemy.models import Base  # noqa: E402


def generate_mermaid_erd() -> str:
    metadata = Base.metadata

    lines = ["erDiagram"]

    # 1. Relationships from Foreign Keys
    relationships = set()
    for table_name, table in sorted(metadata.tables.items()):
        for fk in table.foreign_keys:
            target_table = fk.column.table.name
            # Format: TARGET ||--o{ SOURCE : "references"
            rel = f'    {target_table.upper()} ||--o{{ {table_name.upper()} : "FK_{fk.parent.name}"'
            relationships.add(rel)

    for rel in sorted(relationships):
        lines.append(rel)

    lines.append("")

    # 2. Table definitions with columns and types
    for table_name, table in sorted(metadata.tables.items()):
        lines.append(f"    {table_name.upper()} {{")
        for col in table.columns:
            # Map type to simple clean string
            col_type = str(col.type).split("(")[0].lower()
            if "varchar" in col_type or "text" in col_type or "enum" in col_type:
                type_str = "string"
            elif "bigint" in col_type:
                type_str = "bigint"
            elif "int" in col_type or "boolean" in col_type:
                type_str = "int" if "int" in col_type else "boolean"
            elif "numeric" in col_type or "decimal" in col_type:
                type_str = "decimal"
            elif "datetime" in col_type or "timestamp" in col_type:
                type_str = "datetime"
            elif "json" in col_type:
                type_str = "json"
            else:
                type_str = col_type

            key_tag = ""
            if col.primary_key:
                key_tag = "PK"
            elif col.foreign_keys:
                key_tag = "FK"
            elif col.unique:
                key_tag = "UK"

            col_line = f"        {type_str} {col.name}"
            if key_tag:
                col_line += f" {key_tag}"
            lines.append(col_line)
        lines.append("    }")
        lines.append("")

    return "\n".join(lines)


def generate_full_markdown() -> str:
    mermaid_content = generate_mermaid_erd()
    metadata = Base.metadata

    md_lines = [
        "# Diagrama Entidad-Relación (ERD) — Datamaq Telemetry",
        "",
        "> [!NOTE]",
        "> Este documento se genera de forma 100% automática a partir de los modelos de SQLAlchemy",
        "> (`src/infrastructure/sqlalchemy/models.py`) mediante el script `scripts/generate_erd.py`.",
        "",
        "## 1. Diagrama de Relaciones",
        "",
        "```mermaid",
        mermaid_content,
        "```",
        "",
        "## 2. Detalle de Tablas e Índices",
        "",
    ]

    for table_name, table in sorted(metadata.tables.items()):
        md_lines.append(f"### Tabla `{table_name}`")
        md_lines.append("")
        md_lines.append("| Columna | Tipo SQL | Clave / Restricción | Nullable |")
        md_lines.append("| :--- | :--- | :--- | :--- |")

        for col in table.columns:
            key_info = []
            if col.primary_key:
                key_info.append("**PRIMARY KEY**")
            for fk in sorted(col.foreign_keys, key=lambda x: str(x.target_fullname)):
                key_info.append(f"FK -> `{fk.target_fullname}`")
            if col.unique and not col.primary_key:
                key_info.append("UNIQUE")

            key_str = ", ".join(key_info) if key_info else "-"
            nullable_str = "Sí" if col.nullable else "No"
            md_lines.append(f"| `{col.name}` | `{col.type}` | {key_str} | {nullable_str} |")

        if table.indexes:
            md_lines.append("")
            md_lines.append("**Índices:**")
            for idx in sorted(table.indexes, key=lambda x: str(x.name or "")):
                cols = ", ".join([f"`{c.name}`" for c in idx.columns])
                uniq = " (UNIQUE)" if idx.unique else ""
                md_lines.append(f"- `{idx.name}`{uniq}: ({cols})")

        md_lines.append("")

    md_lines.append("## 3. Matriz de Políticas de Retención y Granularidad (Modelo Activo PRO 60d / Free)")
    md_lines.append("")
    md_lines.append(
        "Conforme a la directiva comercial en `docs/to_www-datamaq.md` y al servicio `PoliticaSuscripcionService`:"
    )
    md_lines.append("")
    md_lines.append(
        "| Tabla | Categoría | Free Privado Básico (Default) | Vitrina Pública Anónima (Opt-in) | Versión PRO (60d Activa) | Estrategia de Purga |"
    )
    md_lines.append("| :--- | :--- | :---: | :---: | :---: | :--- |")
    md_lines.append(
        "| `telemetry_instantaneous` | Series Temporales (V, I, P, FP) | 14 días (gran. horaria/5m) | 30 días (gran. 5 min / 1s) | 365 días (máxima resolución) | Batched `DELETE ... LIMIT 1000` |"
    )
    md_lines.append(
        "| `telemetry_energy` | Acumulados de Energía (kWh) | 14 días | 30 días | 365 días | Batched `DELETE ... LIMIT 1000` |"
    )
    md_lines.append(
        "| `device_status_logs` | Diagnóstico de Conectividad (Wi-Fi, IP) | 7 días | 15 días | 30 días | Batched `DELETE ... LIMIT 1000` |"
    )
    md_lines.append(
        "| `device_alerts` (Resueltas) | Incidentes Cerrados | 14 días | 30 días | 365 días | `WHERE is_resolved = TRUE AND resolved_at < corte` |"
    )
    md_lines.append(
        "| `device_alerts` (Activas) | Incidentes Abiertos | **Indefinida (0 borrado)** | **Indefinida (0 borrado)** | **Indefinida (0 borrado)** | **Preservadas permanentemente** |"
    )
    md_lines.append("")

    return "\n".join(md_lines) + "\n"


def main():
    parser = argparse.ArgumentParser(
        description="Generador automático de Diagrama Entidad-Relación (ERD) para Datamaq Telemetry."
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=os.path.join(ROOT_DIR, "docs", "database_erd.md"),
        help="Ruta de destino del archivo Markdown generado.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verifica si el archivo existente está sincronizado con los modelos sin modificarlo.",
    )
    args = parser.parse_args()

    content = generate_full_markdown()

    if args.check:
        if not os.path.exists(args.output):
            print(f"[!] Error: El archivo {args.output} no existe.", file=sys.stderr)
            sys.exit(1)
        with open(args.output, encoding="utf-8") as f:
            existing = f.read()
        if existing != content:
            print(
                f"[!] El archivo {args.output} está desactualizado respecto a los modelos SQLAlchemy.",
                file=sys.stderr,
            )
            print("    Ejecuta: python scripts/generate_erd.py para actualizarlo.", file=sys.stderr)
            sys.exit(1)
        print(f"[+] El archivo {args.output} está 100% sincronizado con los modelos.")
        sys.exit(0)

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"[+] Diagrama Entidad-Relación generado exitosamente en: {args.output}")


if __name__ == "__main__":
    main()
