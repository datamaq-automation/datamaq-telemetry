"""tests/unit/test_nomenclatura_estructurada.py

Validación de nomenclatura estructurada jerárquica para activos industriales.
Asegura que todos los IDs de nodos, medidores y zonas sigan el patrón semántico esperado.
"""

import re
from pathlib import Path

import yaml


def _cargar_organizaciones() -> dict:
    """Carga el archivo organizaciones.yml"""
    yaml_path = Path("data/organizaciones.yml")
    with open(yaml_path) as f:
        return yaml.safe_load(f)


def test_nodos_siguen_patron_node_org_planta_zona_numero():
    data = _cargar_organizaciones()
    for org in data.get("organizaciones", []):
        for planta in org.get("plantas", []):
            nodos = planta.get("nodos_unifilar", [])
            for nodo in nodos:
                nodo_id = nodo.get("id")
                assert nodo_id.startswith("node-"), f"Nodo {nodo_id} no comienza con 'node-'"
                parts = nodo_id.split("-")
                assert len(parts) >= 4, f"Nodo {nodo_id} no tiene estructura mínima node-org-planta-zona"


def test_medidores_siguen_patron_meter_org_planta_zona_numero():
    data = _cargar_organizaciones()
    for org in data.get("organizaciones", []):
        for planta in org.get("plantas", []):
            medidores = planta.get("medidores", [])
            for medidor in medidores:
                medidor_id = medidor.get("id")
                assert medidor_id.startswith("meter-"), f"Medidor {medidor_id} no comienza con 'meter-'"
                parts = medidor_id.split("-")
                assert len(parts) >= 4, f"Medidor {medidor_id} no tiene estructura mínima meter-org-planta-zona"


def test_zonas_siguen_patron_zone_org_planta_zona():
    data = _cargar_organizaciones()
    for org in data.get("organizaciones", []):
        for planta in org.get("plantas", []):
            zonas = planta.get("zonas", [])
            for zona in zonas:
                zona_id = zona.get("id")
                assert zona_id.startswith("zone-"), f"Zona {zona_id} no comienza con 'zone-'"
                parts = zona_id.split("-")
                assert len(parts) >= 3, f"Zona {zona_id} no tiene estructura mínima zone-org-planta"


def test_nodos_no_contienen_uuids_o_hashes():
    data = _cargar_organizaciones()
    uuid_pattern = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")

    for org in data.get("organizaciones", []):
        for planta in org.get("plantas", []):
            nodos = planta.get("nodos_unifilar", [])
            for nodo in nodos:
                nodo_id = nodo.get("id")
                assert not uuid_pattern.search(nodo_id), f"Nodo {nodo_id} contiene UUID"


def test_nombres_humanizados_tienen_formato_ubicacion_funcion():
    data = _cargar_organizaciones()
    patron_separador = re.compile(r"\s+—\s+")

    for org in data.get("organizaciones", []):
        for planta in org.get("plantas", []):
            nodos = planta.get("nodos_unifilar", [])
            for nodo in nodos:
                nombre = nodo.get("nombre", "")
                if nombre:
                    assert patron_separador.search(nombre), (
                        f"Nodo {nodo.get('id')}: nombre '{nombre}' no tiene formato '<Ubicación> — <Función>'"
                    )

            zonas = planta.get("zonas", [])
            for zona in zonas:
                nombre = zona.get("nombre", "")
                if nombre:
                    assert patron_separador.search(nombre), (
                        f"Zona {zona.get('id')}: nombre '{nombre}' no tiene formato '<Ubicación> — <Función>'"
                    )


def test_referencias_cruzadas_dispositivos_layout_validas():
    data = _cargar_organizaciones()
    for org in data.get("organizaciones", []):
        for planta in org.get("plantas", []):
            zonas_ids = {z.get("id") for z in planta.get("zonas", [])}
            dispositivos = planta.get("dispositivos_layout", [])
            for dispositivo in dispositivos:
                zona_id = dispositivo.get("zona_id")
                if zona_id:
                    assert zona_id in zonas_ids, f"Dispositivo {dispositivo.get('id')}: zona_id '{zona_id}' no existe"
                    assert zona_id.startswith("zone-"), f"zona_id {zona_id} no tiene prefijo zone-"


def test_slugs_unicos_dentro_de_planta():
    data = _cargar_organizaciones()
    for org in data.get("organizaciones", []):
        for planta in org.get("plantas", []):
            all_ids = set()

            for zona in planta.get("zonas", []):
                zona_id = zona.get("id")
                assert zona_id not in all_ids, f"Zona duplicada: {zona_id}"
                all_ids.add(zona_id)

            for nodo in planta.get("nodos_unifilar", []):
                nodo_id = nodo.get("id")
                assert nodo_id not in all_ids, f"Nodo duplicado o conflictivo: {nodo_id}"
                all_ids.add(nodo_id)

            for medidor in planta.get("medidores", []):
                medidor_id = medidor.get("id")
                assert medidor_id not in all_ids, f"Medidor duplicado o conflictivo: {medidor_id}"
                all_ids.add(medidor_id)
