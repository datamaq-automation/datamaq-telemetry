# src/infrastructure/yaml/loaders.py
import glob
import os

import yaml


def cargar_yaml_seguro(file_path: str) -> dict | list | None:
    """Carga y parsea un archivo YAML de forma segura."""
    if not os.path.exists(file_path):
        return None
    try:
        with open(file_path, encoding="utf-8") as f:
            contenido = yaml.safe_load(f)
            if isinstance(contenido, (dict, list)):
                return contenido
    except Exception:
        return None
    return None


def _cargar_unifilar_nodos(planta_folder: str) -> list[dict] | None:
    """Lee nodos de unifilar.yml o unifilar.yaml."""
    candidates = [
        os.path.join(planta_folder, "unifilar.yml"),
        os.path.join(planta_folder, "unifilar.yaml"),
    ]
    for ufile in candidates:
        content = cargar_yaml_seguro(ufile)
        if isinstance(content, dict) and "nodos" in content and isinstance(content["nodos"], list):
            return content["nodos"]
        if isinstance(content, list):
            return [x for x in content if isinstance(x, dict)]
    return None


def _cargar_layout_data(
    planta_folder: str,
) -> tuple[list[dict] | None, list[dict] | None, str | None]:
    """Lee zonas, dispositivos y svg_url desde layout.yml o layout.yaml."""
    candidates = [
        os.path.join(planta_folder, "layout.yml"),
        os.path.join(planta_folder, "layout.yaml"),
    ]
    for lfile in candidates:
        content = cargar_yaml_seguro(lfile)
        if isinstance(content, dict):
            zonas = content.get("zonas") if isinstance(content.get("zonas"), list) else None
            disp = content.get("dispositivos") or content.get("dispositivos_layout")
            dispositivos = disp if isinstance(disp, list) else None
            svg_url = content.get("plano_svg_url")
            return zonas, dispositivos, svg_url
    return None, None, None


def _cargar_planta_modular(planta_folder: str) -> dict | None:
    """Carga la definición y artefactos de una planta modular."""
    planta_id = os.path.basename(planta_folder)
    candidates = [
        os.path.join(planta_folder, "planta.yml"),
        os.path.join(planta_folder, "planta.yaml"),
    ]
    p_data: dict | None = None
    for pfile in candidates:
        content = cargar_yaml_seguro(pfile)
        if isinstance(content, dict):
            p_data = content
            break

    if not p_data:
        return None

    if "id" not in p_data:
        p_data["id"] = planta_id

    nodos = _cargar_unifilar_nodos(planta_folder)
    if nodos is not None:
        p_data["nodos_unifilar"] = nodos

    zonas, dispositivos, svg_url = _cargar_layout_data(planta_folder)
    if zonas is not None:
        p_data["zonas"] = zonas
    if dispositivos is not None:
        p_data["dispositivos_layout"] = dispositivos
    if svg_url is not None:
        p_data["layout_svg_url"] = svg_url

    return p_data


def cargar_organizaciones_modulares(data_dir: str) -> dict[str, dict]:
    """Soporte modular ISA-95: {data_dir}/organizaciones/{org_id}/."""
    cargadas: dict[str, dict] = {}
    pattern_modular = os.path.join(data_dir, "organizaciones", "*")
    for org_folder in glob.glob(pattern_modular):
        if not os.path.isdir(org_folder):
            continue
        org_id = os.path.basename(org_folder)
        candidates = [
            os.path.join(org_folder, "organizacion.yml"),
            os.path.join(org_folder, "organizacion.yaml"),
        ]
        org_data: dict | None = None
        for ofile in candidates:
            content = cargar_yaml_seguro(ofile)
            if isinstance(content, dict):
                org_data = content
                break

        if not org_data:
            continue

        if "id" not in org_data:
            org_data["id"] = org_id

        plantas_list = org_data.setdefault("plantas", [])
        plantas_dir = os.path.join(org_folder, "plantas")
        if os.path.isdir(plantas_dir):
            for planta_folder in glob.glob(os.path.join(plantas_dir, "*")):
                if not os.path.isdir(planta_folder):
                    continue
                p_data = _cargar_planta_modular(planta_folder)
                if p_data:
                    existing = next(
                        (p for p in plantas_list if str(p.get("id")) == str(p_data["id"])),
                        None,
                    )
                    if not existing:
                        plantas_list.append(p_data)

        cargadas[str(org_data["id"])] = org_data
    return cargadas


def _extraer_items_organizaciones(contenido: dict | list) -> list[dict]:
    """Extrae lista de diccionarios de organización desde un payload plano."""
    if isinstance(contenido, list):
        return [x for x in contenido if isinstance(x, dict)]
    if isinstance(contenido, dict):
        if "organizaciones" in contenido and isinstance(contenido["organizaciones"], list):
            return [x for x in contenido["organizaciones"] if isinstance(x, dict)]
        if "id" in contenido and "nombre" in contenido:
            return [contenido]
    return []


def cargar_organizaciones_planas(data_dir: str, cargadas_por_id: dict[str, dict]) -> None:
    """Soporte para archivos consolidados/planos legacy."""
    pattern = os.path.join(data_dir, "**", "*.yml")
    archivos = glob.glob(pattern, recursive=True)
    pattern_yaml = os.path.join(data_dir, "**", "*.yaml")
    archivos.extend(glob.glob(pattern_yaml, recursive=True))

    archivos_submodulares = {
        "planta.yml",
        "planta.yaml",
        "unifilar.yml",
        "unifilar.yaml",
        "layout.yml",
        "layout.yaml",
        "organizacion.yml",
        "organizacion.yaml",
    }

    for filepath in set(archivos):
        basename = os.path.basename(filepath).lower()
        if basename in archivos_submodulares:
            continue

        content = cargar_yaml_seguro(filepath)
        if not content:
            continue

        for item in _extraer_items_organizaciones(content):
            item_id = str(item.get("id"))
            if item_id and item_id not in cargadas_por_id:
                cargadas_por_id[item_id] = item


def cargar_organizaciones_completas(data_dir: str) -> list[dict]:
    """Carga organizaciones combinando estructura modular y archivos planos."""
    cargadas_por_id = cargar_organizaciones_modulares(data_dir)
    cargar_organizaciones_planas(data_dir, cargadas_por_id)
    return list(cargadas_por_id.values())


def cargar_facturas_distribuidora(data_dir: str) -> list[dict]:
    """Carga el histórico de facturas de la distribuidora (`{data_dir}/facturas_distribuidora.yml`).

    Archivo único, sin merge modular/plano: no hay necesidad, es un solo documento por repo.
    """
    contenido = cargar_yaml_seguro(os.path.join(data_dir, "facturas_distribuidora.yml"))
    if isinstance(contenido, dict) and isinstance(contenido.get("facturas"), list):
        return [x for x in contenido["facturas"] if isinstance(x, dict)]
    return []
