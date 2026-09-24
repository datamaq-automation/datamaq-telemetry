"""src/application/use_cases/consultar_balance_energia.py — Verificación de balance de energía en TGBT (ISO 50001 §6.3)."""

from src.application.dtos.sge_dto import BalanceEnergiaResponseDTO
from src.domain.sge.servicios.balance_energia import (
    BalanceEnergiaService,
)
from src.domain.telemetria.entities import TipoNodoUnifilar
from src.domain.telemetria.exceptions import PlantaNoEncontradaError
from src.domain.telemetria.ports import RepositorioOrganizacionesPort


class ConsultarBalanceEnergiaUseCase:
    def __init__(self, repo_organizaciones: RepositorioOrganizacionesPort):
        self._repo_org = repo_organizaciones

    def ejecutar(
        self,
        planta_id: str,
        nodo_id: str | None = None,
        energia_padre_kwh: float | None = None,
        energias_hijos_kwh: list[float] | None = None,
        thd_i_promedio_pct: float | None = None,
    ) -> BalanceEnergiaResponseDTO:
        planta = self._repo_org.obtener_planta_por_id(planta_id)
        if not planta:
            raise PlantaNoEncontradaError(f"Planta {planta_id} no encontrada.")

        nodos = self._repo_org.obtener_nodos_unifilar(planta_id)
        nodo_padre = None
        if nodo_id:
            nodo_padre = next((n for n in nodos if n.id == nodo_id), None)
        else:
            nodo_padre = next(
                (n for n in nodos if n.tipo in (TipoNodoUnifilar.TGBT, TipoNodoUnifilar.TRANSFORMADOR)),
                None,
            )

        padre_id = nodo_padre.id if nodo_padre else (nodo_id or "desconocido")
        padre_nombre = nodo_padre.nombre if nodo_padre else "TGBT Cabecera"

        # Si se pasa energia_padre_kwh explícito, se usa directo. Si no, se busca el documento
        # de energía (tipo_dato="energia") más reciente de la planta — puede venir de un
        # proveedor distinto al de potencia (ej. UPP: CAMMESA factura energía, EdeLAP potencia,
        # ver FacturaDistribuidora en domain/sge/entities.py). Sin facturas de energía cargadas,
        # cae al comportamiento anterior (0.0).
        if energia_padre_kwh is not None:
            e_padre = float(energia_padre_kwh)
        else:
            facturas_energia = [
                f for f in self._repo_org.obtener_facturas_planta(planta_id) if f.tipo_dato == "energia"
            ]
            e_padre = (facturas_energia[0].energia_facturada_kwh or 0.0) if facturas_energia else 0.0
        e_hijos = energias_hijos_kwh if energias_hijos_kwh is not None else []

        resultado = BalanceEnergiaService.evaluar_balance(
            energia_padre_kwh=e_padre,
            energias_hijos_kwh=e_hijos,
            thd_i_promedio_pct=thd_i_promedio_pct,
        )

        return BalanceEnergiaResponseDTO(
            planta_id=planta_id,
            nodo_padre_id=padre_id,
            nodo_padre_nombre=padre_nombre,
            energia_padre_kwh=resultado.energia_padre_kwh,
            energia_hijos_sumada_kwh=resultado.energia_hijos_sumada_kwh,
            residual_kwh=resultado.residual_kwh,
            residual_porcentual=resultado.residual_porcentual,
            estado=resultado.estado.value,
            es_auditable_iso50001=resultado.es_auditable_iso50001,
            detalle=resultado.detalle,
            thd_i_promedio_pct=resultado.thd_i_promedio_pct,
        )
