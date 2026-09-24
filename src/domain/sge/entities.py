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


@dataclass(frozen=True)
class FacturaDistribuidora:
    """Factura mensual de la distribuidora, una por planta por período (histórico, no se pisa).

    Evidencia documental para ISO 50001 §6.3 (balance de energía) y §9.1 (EnPI de potencia
    y energía facturada). Se carga por commit al YAML (`data/facturas_distribuidora.yml`),
    nunca por API: ver `decisions/2026-09-24_factura-distribuidora-yaml.md`.

    Potencia y su valor van discriminados Punta / Fuera de Punta porque así factura la
    distribuidora en tarifas de Media Tensión (confirmado con una factura real EDELAP,
    tarifa T5M12, ver `specs/factura-distribuidora.md` §2.1): un único campo "potencia
    contratada" perdería esa distinción tarifaria.
    """

    id: str
    planta_id: str
    periodo: str
    distribuidora: str
    numero_factura: str
    tarifa: str
    dias_facturados: int
    energia_activa_punta_kwh: float
    energia_activa_resto_kwh: float
    energia_activa_valle_kwh: float
    potencia_contratada_punta_kw: float
    potencia_contratada_fuera_punta_kw: float
    potencia_adquirida_punta_kw: float
    potencia_adquirida_fuera_punta_kw: float
    importe_potencia_ars: float
    importe_energia_ars: float
    importe_total_ars: float
    fuente_archivo: str | None = None
    cargada_en: str | None = None

    @property
    def energia_facturada_kwh(self) -> float:
        return self.energia_activa_punta_kwh + self.energia_activa_resto_kwh + self.energia_activa_valle_kwh

    @property
    def potencia_excedida_punta_kw(self) -> float:
        return max(0.0, self.potencia_adquirida_punta_kw - self.potencia_contratada_punta_kw)

    @property
    def potencia_excedida_fuera_punta_kw(self) -> float:
        return max(0.0, self.potencia_adquirida_fuera_punta_kw - self.potencia_contratada_fuera_punta_kw)

    @property
    def valor_energia_ars_kwh_promedio(self) -> float:
        return self.importe_energia_ars / self.energia_facturada_kwh if self.energia_facturada_kwh else 0.0
