from src.domain.telemetria.entities import (
    DispositivoLayout,
    InstalacionMedidor,
    NodoUnifilar,
    Organizacion,
    Planta,
    ZonaPlanta,
)
from src.domain.telemetria.ports import RepositorioOrganizacionesPort
from src.domain.telemetria.value_objects import (
    CoordenadasZona,
    PosicionLayout,
    TipoNodoUnifilar,
)
from src.infrastructure.yaml.loaders import cargar_organizaciones_completas


class YamlOrganizacionesRepository(RepositorioOrganizacionesPort):
    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir

    def _cargar_organizaciones_raw(self) -> list[dict]:
        return cargar_organizaciones_completas(self.data_dir)

    @staticmethod
    def _dict_to_organizacion(d: dict) -> Organizacion:
        # `modo_free`, `plan_id` y `pro_vence_en` ya no se leen del YAML: son estado
        # comercial (Suscripcion, MySQL). Si alguien los deja en el archivo, se ignoran.
        return Organizacion(
            id=str(d["id"]),
            nombre=str(d["nombre"]),
            cuit=d.get("cuit"),
            email_contacto=d.get("email_contacto"),
            telefono_contacto=d.get("telefono_contacto"),
        )

    def obtener_por_id(self, organizacion_id: str) -> Organizacion | None:
        for raw in self._cargar_organizaciones_raw():
            if str(raw.get("id")) == str(organizacion_id):
                return self._dict_to_organizacion(raw)
        return None

    def listar_organizaciones(self) -> list[Organizacion]:
        orgs = []
        for raw in self._cargar_organizaciones_raw():
            if "id" in raw and "nombre" in raw:
                orgs.append(self._dict_to_organizacion(raw))
        return orgs

    def obtener_planta_por_id(self, planta_id: str) -> Planta | None:
        for raw in self._cargar_organizaciones_raw():
            plantas = raw.get("plantas", [])
            for p in plantas:
                if str(p.get("id")) == str(planta_id):
                    return Planta(
                        id=str(p["id"]),
                        organizacion_id=str(raw["id"]),
                        nombre=str(p["nombre"]),
                        direccion=p.get("direccion"),
                        latitud=p.get("latitud"),
                        longitud=p.get("longitud"),
                        layout_svg_url=p.get("layout_svg_url"),
                    )
        return None

    def listar_plantas(self, organizacion_id: str | None = None) -> list[Planta]:
        plantas = []
        for raw in self._cargar_organizaciones_raw():
            org_id = str(raw.get("id"))
            if organizacion_id and org_id != str(organizacion_id):
                continue
            for p in raw.get("plantas", []):
                plantas.append(
                    Planta(
                        id=str(p["id"]),
                        organizacion_id=org_id,
                        nombre=str(p["nombre"]),
                        direccion=p.get("direccion"),
                        latitud=p.get("latitud"),
                        longitud=p.get("longitud"),
                        layout_svg_url=p.get("layout_svg_url"),
                    )
                )
        return plantas

    def obtener_nodos_unifilar(self, planta_id: str) -> list[NodoUnifilar]:
        for raw in self._cargar_organizaciones_raw():
            for p in raw.get("plantas", []):
                if str(p.get("id")) == str(planta_id):
                    nodos = []
                    for n in p.get("nodos_unifilar", []):
                        tipo_raw = str(n.get("tipo", "CARGA")).upper()
                        tipo = (
                            TipoNodoUnifilar[tipo_raw]
                            if tipo_raw in TipoNodoUnifilar.__members__
                            else TipoNodoUnifilar.CARGA
                        )
                        nodos.append(
                            NodoUnifilar(
                                id=str(n["id"]),
                                planta_id=planta_id,
                                nombre=str(n["nombre"]),
                                tipo=tipo,
                                tension_nominal_v=float(n.get("tension_nominal_v", 380.0)),
                                parent_id=n.get("padre_id") or n.get("parent_id"),
                                device_id=n.get("dispositivo_id") or n.get("device_id"),
                                capacidad_nominal_kva=float(n["capacidad_nominal_kva"])
                                if n.get("capacidad_nominal_kva") is not None
                                else None,
                                potencia_nominal_kw=float(n["potencia_nominal_kw"])
                                if n.get("potencia_nominal_kw") is not None
                                else None,
                                uso_significativo=bool(n.get("uso_significativo", False)),
                                categoria_uso=n.get("categoria_uso"),
                                variable_relevante=n.get("variable_relevante"),
                                categoria_tarifaria=n.get("categoria_tarifaria"),
                                penalizacion_reactiva_aplica=(
                                    bool(n["penalizacion_reactiva_aplica"])
                                    if n.get("penalizacion_reactiva_aplica") is not None
                                    else None
                                ),
                                fuente_dato=n.get("fuente_dato"),
                                notas_metrologicas=n.get("notas_metrologicas"),
                            )
                        )

                    return nodos
        return []

    def obtener_zonas_planta(self, planta_id: str) -> list[ZonaPlanta]:
        for raw in self._cargar_organizaciones_raw():
            for p in raw.get("plantas", []):
                if str(p.get("id")) == str(planta_id):
                    zonas = []
                    for z in p.get("zonas", []):
                        coords_raw = z.get("coordenadas", {})
                        coords = CoordenadasZona(
                            x_porcentaje=coords_raw.get("x", 0.0),
                            y_porcentaje=coords_raw.get("y", 0.0),
                            ancho_porcentaje=coords_raw.get("ancho", 0.0),
                            alto_porcentaje=coords_raw.get("alto", 0.0),
                        )
                        zonas.append(
                            ZonaPlanta(
                                id=str(z["id"]),
                                planta_id=planta_id,
                                nombre=str(z["nombre"]),
                                coordenadas=coords,
                            )
                        )
                    return zonas
        return []

    def obtener_dispositivos_layout(self, planta_id: str) -> list[DispositivoLayout]:
        for raw in self._cargar_organizaciones_raw():
            for p in raw.get("plantas", []):
                if str(p.get("id")) == str(planta_id):
                    disps = []
                    for d in p.get("dispositivos_layout", []):
                        pos_raw = d.get("posicion", {})
                        pos = PosicionLayout(
                            x_porcentaje=pos_raw.get("x", 0.0),
                            y_porcentaje=pos_raw.get("y", 0.0),
                        )
                        disps.append(
                            DispositivoLayout(
                                id=str(d.get("id", f"lay-{d.get('dispositivo_id')}")),
                                planta_id=planta_id,
                                device_id=str(d.get("dispositivo_id") or d.get("device_id")),
                                posicion=pos,
                                zona_id=d.get("zona_id"),
                            )
                        )
                    return disps
        return []

    def obtener_instalacion_medidor(self, dispositivo_id: str) -> InstalacionMedidor | None:
        for raw in self._cargar_organizaciones_raw():
            for p in raw.get("plantas", []):
                for m in p.get("medidores", []) or []:
                    if str(m.get("id")) == str(dispositivo_id):
                        return InstalacionMedidor(
                            dispositivo_id=str(m["id"]),
                            tag_ubicacion=m.get("tag_ubicacion"),
                            tipo_instalacion=m.get("tipo_instalacion"),
                            fases_con_ti=m.get("fases_con_ti"),
                        )
        return None
