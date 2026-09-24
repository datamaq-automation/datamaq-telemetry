# src/infrastructure/yaml/repositories/organizaciones_repository.py
import structlog

from src.domain.sge.entities import FacturaDistribuidora
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
    CoordenadasNodoUnifilar,
    CoordenadasZona,
    InterruptorCabecera,
    MetadatosPlaca,
    PosicionLayout,
    TipoNodoUnifilar,
)
from src.infrastructure.yaml.loaders import cargar_facturas_distribuidora, cargar_organizaciones_completas

logger = structlog.get_logger(__name__)


def _float_opt(f: dict, clave: str) -> float | None:
    valor = f.get(clave)
    return float(valor) if valor is not None else None


def _parsear_factura(f: dict) -> FacturaDistribuidora:
    planta_id = str(f["planta_id"])
    periodo = str(f["periodo"])
    # Sin `tipo_dato` declarado (YAML legacy previo a la distinción potencia/energía),
    # se asume "potencia": era el único tipo de dato que existía antes de este cambio.
    tipo_dato = str(f.get("tipo_dato") or "potencia")
    return FacturaDistribuidora(
        id=str(f.get("id") or f"{planta_id}-{periodo}-{tipo_dato}"),
        planta_id=planta_id,
        periodo=periodo,
        proveedor=str(f.get("proveedor") or f.get("distribuidora", "")),
        tipo_dato=tipo_dato,  # type: ignore[arg-type]
        numero_factura=str(f.get("numero_factura", "")),
        importe_total_ars=float(f.get("importe_total_ars", 0.0)),
        tarifa=f.get("tarifa"),
        dias_facturados=int(f["dias_facturados"]) if f.get("dias_facturados") is not None else None,
        energia_activa_punta_kwh=_float_opt(f, "energia_activa_punta_kwh"),
        energia_activa_resto_kwh=_float_opt(f, "energia_activa_resto_kwh"),
        energia_activa_valle_kwh=_float_opt(f, "energia_activa_valle_kwh"),
        energia_activa_total_kwh=_float_opt(f, "energia_activa_total_kwh"),
        potencia_contratada_punta_kw=_float_opt(f, "potencia_contratada_punta_kw"),
        potencia_contratada_fuera_punta_kw=_float_opt(f, "potencia_contratada_fuera_punta_kw"),
        potencia_adquirida_punta_kw=_float_opt(f, "potencia_adquirida_punta_kw"),
        potencia_adquirida_fuera_punta_kw=_float_opt(f, "potencia_adquirida_fuera_punta_kw"),
        importe_potencia_ars=_float_opt(f, "importe_potencia_ars"),
        importe_energia_ars=_float_opt(f, "importe_energia_ars"),
        fuente_archivo=f.get("fuente_archivo"),
        cargada_en=f.get("cargada_en"),
    )


def _parsear_coordenadas(n: dict) -> CoordenadasNodoUnifilar | None:
    if "coordenadas" not in n or not isinstance(n["coordenadas"], dict):
        return None
    c = n["coordenadas"]
    return CoordenadasNodoUnifilar(
        x=float(c.get("x", 0.0)),
        y=float(c.get("y", 0.0)),
        ancho=float(c["ancho"]) if c.get("ancho") is not None else None,
        orientacion=c.get("orientacion"),
    )


def _parsear_interruptor(n: dict) -> InterruptorCabecera | None:
    if "interruptor_cabecera" not in n or not isinstance(n["interruptor_cabecera"], dict):
        return None
    ic = n["interruptor_cabecera"]
    in_val = ic.get("in_a") if ic.get("in_a") is not None else ic.get("in_A")
    icu_val = ic.get("icu_ka") if ic.get("icu_ka") is not None else ic.get("icu_kA")
    return InterruptorCabecera(
        tag=str(ic.get("tag", "")),
        tipo=ic.get("tipo"),
        in_a=float(in_val) if in_val is not None else None,
        icu_ka=float(icu_val) if icu_val is not None else None,
        estado=str(ic.get("estado", "cerrado")),
    )


def _parsear_metadatos_placa(n: dict) -> MetadatosPlaca | None:
    if "metadatos_placa" not in n or not isinstance(n["metadatos_placa"], dict):
        return None
    mp = dict(n["metadatos_placa"])
    known_keys = {
        "potencia_nominal_kva",
        "relacion_tension_kv",
        "vsc_porcentaje",
        "grupo_conexion",
        "corriente_nominal_a",
        "icw_ka",
        "frecuencia_hz",
        "calibre_in_a",
        "cable_seccion",
        "longitud_estimada_m",
        "tension_nominal_v",
        "categoria_tarifaria",
        "trafo_asociado_kva",
        "corriente_barra_a",
        "proteccion_in_a",
    }
    if "corriente_nominal_A" in mp and "corriente_nominal_a" not in mp:
        mp["corriente_nominal_a"] = mp.pop("corriente_nominal_A")
    if "icw_kA" in mp and "icw_ka" not in mp:
        mp["icw_ka"] = mp.pop("icw_kA")
    if "calibre_in_A" in mp and "calibre_in_a" not in mp:
        mp["calibre_in_a"] = mp.pop("calibre_in_A")

    kwargs = {k: v for k, v in mp.items() if k in known_keys}
    adicionales = {k: v for k, v in mp.items() if k not in known_keys}
    return MetadatosPlaca(**kwargs, datos_adicionales=adicionales if adicionales else None)


def _parsear_nodo_unifilar(n: dict, planta_id: str) -> NodoUnifilar:
    tipo_raw = str(n.get("tipo", "CARGA")).upper()
    if tipo_raw in TipoNodoUnifilar.__members__:
        tipo = TipoNodoUnifilar[tipo_raw]
    else:
        structlog.get_logger(__name__).warning(
            "unifilar_tipo_no_reconocido",
            planta_id=planta_id,
            nodo_id=n.get("id"),
            tipo_raw=tipo_raw,
            fallback="carga",
        )
        tipo = TipoNodoUnifilar.CARGA

    return NodoUnifilar(
        id=str(n["id"]),
        planta_id=planta_id,
        nombre=str(n["nombre"]),
        tipo=tipo,
        tension_nominal_v=float(n.get("tension_nominal_v", 380.0)),
        parent_id=n.get("padre_id") or n.get("parent_id"),
        device_id=n.get("dispositivo_id") or n.get("device_id"),
        capacidad_nominal_kva=float(n["capacidad_nominal_kva"]) if n.get("capacidad_nominal_kva") is not None else None,
        potencia_nominal_kw=float(n["potencia_nominal_kw"]) if n.get("potencia_nominal_kw") is not None else None,
        uso_significativo=bool(n.get("uso_significativo", False)),
        categoria_uso=n.get("categoria_uso"),
        variable_relevante=n.get("variable_relevante"),
        orden=int(n.get("orden", 0)),
        categoria_tarifaria=n.get("categoria_tarifaria"),
        penalizacion_reactiva_aplica=(
            bool(n["penalizacion_reactiva_aplica"]) if n.get("penalizacion_reactiva_aplica") is not None else None
        ),
        fuente_dato=n.get("fuente_dato"),
        notas_metrologicas=n.get("notas_metrologicas"),
        coordenadas=_parsear_coordenadas(n),
        metadatos_placa=_parsear_metadatos_placa(n),
        interruptor_cabecera=_parsear_interruptor(n),
        es_pasante=bool(n.get("es_pasante", False)),
    )


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
                    return [_parsear_nodo_unifilar(n, planta_id) for n in p.get("nodos_unifilar", [])]
        return []

    def obtener_lineas_base_planta(self, planta_id: str) -> list[dict]:
        for raw in self._cargar_organizaciones_raw():
            for p in raw.get("plantas", []):
                if str(p.get("id")) == str(planta_id):
                    lineas = []
                    for n in p.get("nodos_unifilar", []):
                        for lb in n.get("lineas_base", []):
                            linea_copia = dict(lb)
                            linea_copia["nodo_id"] = n.get("id")
                            linea_copia["nodo_nombre"] = n.get("nombre")
                            lineas.append(linea_copia)
                    return lineas
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
        disp_id_norm = str(dispositivo_id).replace(":", "").upper()
        for raw in self._cargar_organizaciones_raw():
            for p in raw.get("plantas", []):
                for m in p.get("medidores", []) or []:
                    m_id = str(m.get("id", ""))
                    alias_ids = [str(a) for a in m.get("alias_ids", [])]
                    device_uid = str(m.get("device_uid", "")).replace(":", "").upper()
                    if (
                        str(dispositivo_id) == m_id
                        or str(dispositivo_id) in alias_ids
                        or (disp_id_norm and disp_id_norm == device_uid)
                    ):
                        return InstalacionMedidor(
                            dispositivo_id=str(dispositivo_id),
                            tag_ubicacion=m.get("tag_ubicacion"),
                            tipo_instalacion=m.get("tipo_instalacion"),
                            fases_con_ti=m.get("fases_con_ti"),
                            ct_fases_invertidas=m.get("ct_fases_invertidas"),
                            correccion_angular_fases=m.get("correccion_angular_fases"),
                            invertido=m.get("invertido"),
                            orden_fases=m.get("orden_fases"),
                        )
        return None

    def obtener_facturas_planta(self, planta_id: str) -> list[FacturaDistribuidora]:
        facturas = [
            _parsear_factura(f)
            for f in cargar_facturas_distribuidora(self.data_dir)
            if str(f.get("planta_id")) == str(planta_id)
        ]
        return sorted(facturas, key=lambda f: f.periodo, reverse=True)
