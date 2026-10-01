"""src/domain/sge/entities.py."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

CategoriaSge = Literal[
    "politica",
    "operacion",
    "mantenimiento",
    "normativa_enre",
    "metas_enpi",
]

CATEGORIAS_SGE_VALIDAS: frozenset[str] = frozenset(
    {
        "politica",
        "operacion",
        "mantenimiento",
        "normativa_enre",
        "metas_enpi",
    }
)


@dataclass(frozen=True)
class ArticuloSge:
    """Entidad inmutable que representa un artículo o procedimiento del SGE ISO 50001."""

    id: str
    titulo: str
    categoria: CategoriaSge
    roles_permitidos: tuple[str, ...]
    resumen: str
    puntos_clave: tuple[str, ...]
    acciones_inmediatas: tuple[str, ...]
    referencia_iso: str
    documento_url: str | None = None

    def es_visible_para(self, rol: str) -> bool:
        """Determina si el artículo es visible para el rol dado (case-insensitive)."""
        rol_normalizado = rol.strip().lower()
        return rol_normalizado in (r.lower() for r in self.roles_permitidos)


@dataclass(frozen=True)
class RegistroCapacitacionSge:
    """Evidencia inmutable de competencia y toma de conciencia (ISO 50001 §7.2 / §7.3)."""

    id: str
    usuario_id: str
    articulo_id: str
    rol_usuario: str
    fecha_completado: datetime
    version_doc: str
    comentarios: str | None = None


TipoDatoFactura = Literal["potencia", "energia"]


@dataclass(frozen=True)
class FacturaDistribuidora:
    """Un documento de facturación de la distribuidora: potencia O energía, no ambas.

    Evidencia documental para ISO 50001 §6.3 (balance de energía) y §9.1 (EnPI de potencia
    y energía facturada). Se carga por commit al YAML (`data/facturas_distribuidora.yml`),
    nunca por API: ver `decisions/2026-09-24_factura-distribuidora-yaml.md`.

    Potencia y energía pueden venir facturadas por proveedores DISTINTOS en la misma planta:
    confirmado por el dueño que UPP recibe la potencia de EdeLAP y la energía de CAMMESA en dos
    PDFs separados del mismo período (ver `specs/factura-distribuidora.md` §1, nota 2026-09-24).
    Por eso cada instancia es un documento (`tipo_dato`), no "el período completo" — dos
    instancias con el mismo `planta_id` y `periodo` pero distinto `tipo_dato` representan el
    mismo mes facturado por dos proveedores. Un registro `tipo_dato="potencia"` tiene poblados
    los campos de potencia (los de energía facturada quedan en `None`) y viceversa.

    Un documento de potencia trae potencia y, si la factura la informa, la energía registrada
    (`energia_registrada_*`, `energia_reactiva_*`); nunca energía facturada (decisión
    `2026-09-28_energia-registrada-edelap.md`, D1 a D3). La registrada es la lectura del medidor de
    la distribuidora; la facturada (`energia_activa_*`) es la que cobra quien vende la energía
    (UPP: CAMMESA). Por eso `energia_facturada_kwh` no mira los campos de registrada.

    Potencia y su valor van discriminados Punta / Fuera de Punta porque así factura la
    distribuidora en tarifas de Media Tensión (confirmado con una factura real EDELAP,
    tarifa T5M12): un único campo "potencia contratada" perdería esa distinción tarifaria.
    """

    id: str
    planta_id: str
    periodo: str
    proveedor: str
    tipo_dato: TipoDatoFactura
    numero_factura: str
    importe_total_ars: float
    tarifa: str | None = None
    dias_facturados: int | None = None
    energia_activa_punta_kwh: float | None = None
    energia_activa_resto_kwh: float | None = None
    energia_activa_valle_kwh: float | None = None
    energia_activa_total_kwh: float | None = None
    potencia_contratada_punta_kw: float | None = None
    potencia_contratada_fuera_punta_kw: float | None = None
    potencia_adquirida_punta_kw: float | None = None
    potencia_adquirida_fuera_punta_kw: float | None = None
    importe_potencia_ars: float | None = None
    importe_energia_ars: float | None = None
    energia_registrada_punta_kwh: float | None = None
    energia_registrada_resto_kwh: float | None = None
    energia_registrada_valle_kwh: float | None = None
    energia_registrada_total_kwh: float | None = None  # el impreso en la factura, no la suma
    energia_reactiva_punta_kvarh: float | None = None
    energia_reactiva_resto_kvarh: float | None = None
    energia_reactiva_valle_kvarh: float | None = None
    fuente_archivo: str | None = None
    cargada_en: str | None = None

    @property
    def energia_facturada_kwh(self) -> float | None:
        """Total facturado del período: el explícito (proveedores que no discriminan por franja,
        ej. CAMMESA) o la suma Punta+Resto+Valle (proveedores que sí, ej. EdeLAP)."""
        if self.energia_activa_total_kwh is not None:
            return self.energia_activa_total_kwh
        if (
            self.energia_activa_punta_kwh is None
            or self.energia_activa_resto_kwh is None
            or self.energia_activa_valle_kwh is None
        ):
            return None
        return self.energia_activa_punta_kwh + self.energia_activa_resto_kwh + self.energia_activa_valle_kwh

    @property
    def potencia_excedida_punta_kw(self) -> float | None:
        if self.potencia_adquirida_punta_kw is None or self.potencia_contratada_punta_kw is None:
            return None
        return max(0.0, self.potencia_adquirida_punta_kw - self.potencia_contratada_punta_kw)

    @property
    def potencia_excedida_fuera_punta_kw(self) -> float | None:
        if self.potencia_adquirida_fuera_punta_kw is None or self.potencia_contratada_fuera_punta_kw is None:
            return None
        return max(0.0, self.potencia_adquirida_fuera_punta_kw - self.potencia_contratada_fuera_punta_kw)

    @property
    def valor_energia_ars_kwh_promedio(self) -> float | None:
        energia = self.energia_facturada_kwh
        if energia is None or self.importe_energia_ars is None or energia == 0:
            return None
        return self.importe_energia_ars / energia

    @property
    def valor_potencia_ars_kw_promedio(self) -> float | None:
        """Precio promedio por kW ($/kW) cobrado en la factura de potencia.

        Se calcula como el importe total de potencia dividido la potencia total facturada
        (contratada + excedida si hubo exceso, o contratada si no).
        None si no hay importe de potencia o la potencia base es 0 / None.
        """
        if self.importe_potencia_ars is None:
            return None
        pot_punta = self.potencia_contratada_punta_kw or 0.0
        pot_fp = self.potencia_contratada_fuera_punta_kw or 0.0
        exc_punta = self.potencia_excedida_punta_kw or 0.0
        exc_fp = self.potencia_excedida_fuera_punta_kw or 0.0
        total_kw = pot_punta + pot_fp + exc_punta + exc_fp
        if total_kw <= 0.0:
            return None
        return self.importe_potencia_ars / total_kw
