"""src/adapters/gateways/in_memory_documentacion_sge_repository.py."""
from src.domain.sge.entities import ArticuloSge
from src.domain.sge.ports import RepositorioDocumentacionSgePort

_CATALOGO_INICIAL_SGE: tuple[ArticuloSge, ...] = (
    ArticuloSge(
        id="sge-op-01",
        titulo="Procedimiento Operativo: Paradas Operativas y Horario Pico",
        categoria="operacion",
        roles_permitidos=("operador", "mantenimiento"),
        resumen="Instrucciones de apagado secuencial para evitar demanda máxima...",
        puntos_clave=(
            "Escalonamiento de arranque de grandes motores",
            "Monitoreo de potencia activa instantánea en TGBT",
        ),
        acciones_inmediatas=("No encender dos compresores simultáneos en horario pico (18 a 23 hs)",),
        referencia_iso="Cláusula 8.1 - Planificación y Control Operativo",
        documento_url="/archivos/sge/IT-EN-03.pdf",
    ),
    ArticuloSge(
        id="sge-pol-01",
        titulo="Política Energética y Compromiso de Desempeño Energético Madygraf",
        categoria="politica",
        roles_permitidos=("operador", "mantenimiento", "ingeniero", "admin"),
        resumen=(
            "Declaración formal de la cooperativa Madygraf hacia la mejora continua de "
            "la eficiencia energética y reducción de emisiones."
        ),
        puntos_clave=(
            "Compromiso de dirección y asamblea cooperativa",
            "Disponibilidad de información y recursos necesarios",
            "Cumplimiento legal y normativo ENRE",
        ),
        acciones_inmediatas=("Reportar cualquier desvío energético o fuga de aire comprimido detectada en planta",),
        referencia_iso="Cláusula 5.2 - Política Energética",
        documento_url="/archivos/sge/POL-SGE-01.pdf",
    ),
    ArticuloSge(
        id="sge-mto-01",
        titulo="Mantenimiento Preventivo: Compensación de Reactiva y Banco de Capacitores",
        categoria="mantenimiento",
        roles_permitidos=("mantenimiento", "ingeniero"),
        resumen=(
            "Protocolo de inspección mensual y mantenimiento térmico del banco automático de capacitores en TGBT."
        ),
        puntos_clave=(
            "Termografía de contactores y pasos de compensación",
            "Medición de corriente por paso y capacitancia residual",
            "Inspección de ventilación forzada en tableros",
        ),
        acciones_inmediatas=("Desconectar paso de capacitor si se observa corriente desequilibrada > 10% entre fases",),
        referencia_iso="Cláusula 8.1 - Planificación y Control Operativo",
        documento_url="/archivos/sge/IT-MTO-04.pdf",
    ),
    ArticuloSge(
        id="sge-enre-01",
        titulo="Normativa ENRE Res. 85/2024: Régimen Sancionatorio de Factor de Potencia",
        categoria="normativa_enre",
        roles_permitidos=("ingeniero", "admin"),
        resumen=(
            "Criterios técnicos para mantener factor de potencia inductivo tg φ ≤ 0.426 "
            "(cos φ ≥ 0.92) y evitar penalizaciones de Edenor."
        ),
        puntos_clave=(
            "Umbral mínimo legal cos φ = 0.95 proyectado",
            "Monitoreo continuo en medidores de cabecera",
            "Plan de contingencia ante fallas de banco",
        ),
        acciones_inmediatas=("Verificar estado de pasos automáticos ante cos φ global inferior a 0.92",),
        referencia_iso="Cláusula 4.2 - Requisitos Legales y Otros Requisitos",
        documento_url="/archivos/sge/RES-ENRE-85-2024.pdf",
    ),
    ArticuloSge(
        id="sge-enpi-01",
        titulo="Indicadores de Desempeño Energético (EnPI): Línea Base Rotativas",
        categoria="metas_enpi",
        roles_permitidos=("ingeniero", "admin"),
        resumen=(
            "Monitoreo y cálculo del consumo específico de energía eléctrica "
            "(kWh / millar de pliegos impresos) en rotativas de producción."
        ),
        puntos_clave=(
            "Correlación de telemetría de potencia con producción declarada",
            "Línea de base energética (EnB) histórica",
            "Seguimiento de meta de reducción del 4% anual",
        ),
        acciones_inmediatas=(
            "Analizar desvíos de consumo específico superiores al 5% respecto a la línea base en el turno",
        ),
        referencia_iso="Cláusula 6.5 - Indicadores de Desempeño Energético",
        documento_url="/archivos/sge/ENPI-REP-2026.pdf",
    ),
)


class InMemoryDocumentacionSgeRepository(RepositorioDocumentacionSgePort):
    """Repositorio en memoria con el catálogo documental oficial del SGE ISO 50001."""

    def __init__(self, articulos: tuple[ArticuloSge, ...] = _CATALOGO_INICIAL_SGE):
        self._articulos = {a.id: a for a in articulos}

    def listar_todos(self) -> list[ArticuloSge]:
        return list(self._articulos.values())

    def listar_por_rol(self, rol: str) -> list[ArticuloSge]:
        return [a for a in self._articulos.values() if a.es_visible_para(rol)]

    def obtener_por_id(self, articulo_id: str) -> ArticuloSge | None:
        return self._articulos.get(articulo_id)
