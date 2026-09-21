"""src/application/use_cases/consultar_nodo_unifilar.py."""

from datetime import datetime, timezone

from src.application.dtos.planta_estructura_dto import (
    AgregadoPorFaseDTO,
    BancoRecomendadoDTO,
    CompensacionHistoricaDTO,
    FaseAgregadaDTO,
    PuntoPotenciaNodoUnifilarDTO,
    ResumenNodoUnifilarDTO,
)
from src.application.dtos.telemetria_dto import EnergiaAgregadaDTO
from src.application.use_cases.agregacion_dispositivos import calcular_historico, calcular_resumen
from src.application.use_cases.consultar_telemetria import ConsultarTelemetriaUseCase
from src.domain.telemetria.analizador_reactiva import DimensionadorCompensacionService
from src.domain.telemetria.entities import NodoUnifilar, Planta
from src.domain.telemetria.exceptions import PlantaNoEncontradaError
from src.domain.telemetria.ports import RepositorioOrganizacionesPort, RepositorioTelemetriaPort
from src.domain.telemetria.servicios.agregador_dispositivos import AgregadoPorFase
from src.domain.telemetria.servicios.arbol_unifilar import ArbolUnifilarService
from src.domain.telemetria.value_objects import TipoNodoUnifilar


def _mapear_agregado_por_fase(ag: AgregadoPorFase | None) -> AgregadoPorFaseDTO | None:
    if ag is None:
        return None
    return AgregadoPorFaseDTO(
        fase_r=FaseAgregadaDTO(
            voltage_V=ag.fase_r.voltage_V,
            current_A=ag.fase_r.current_A,
            net_active_power_W=ag.fase_r.net_active_power_W,
            net_reactive_power_VAR=ag.fase_r.net_reactive_power_VAR,
            net_apparent_power_VA=ag.fase_r.net_apparent_power_VA,
            power_factor=ag.fase_r.power_factor,
            desbalance_tension_pct=ag.fase_r.desbalance_tension_pct,
        ),
        fase_s=FaseAgregadaDTO(
            voltage_V=ag.fase_s.voltage_V,
            current_A=ag.fase_s.current_A,
            net_active_power_W=ag.fase_s.net_active_power_W,
            net_reactive_power_VAR=ag.fase_s.net_reactive_power_VAR,
            net_apparent_power_VA=ag.fase_s.net_apparent_power_VA,
            power_factor=ag.fase_s.power_factor,
            desbalance_tension_pct=ag.fase_s.desbalance_tension_pct,
        ),
        fase_t=FaseAgregadaDTO(
            voltage_V=ag.fase_t.voltage_V,
            current_A=ag.fase_t.current_A,
            net_active_power_W=ag.fase_t.net_active_power_W,
            net_reactive_power_VAR=ag.fase_t.net_reactive_power_VAR,
            net_apparent_power_VA=ag.fase_t.net_apparent_power_VA,
            power_factor=ag.fase_t.power_factor,
            desbalance_tension_pct=ag.fase_t.desbalance_tension_pct,
        ),
    )


class ConsultarNodoUnifilarUseCase:
    """Telemetría agregada de un nodo del unifilar: suma de sus medidores frontera."""

    def __init__(
        self,
        repo_organizaciones: RepositorioOrganizacionesPort,
        repo_telemetria: RepositorioTelemetriaPort,
        consultar_telemetria: ConsultarTelemetriaUseCase,
    ):
        self.repo_organizaciones = repo_organizaciones
        self.repo_telemetria = repo_telemetria
        self.consultar_telemetria = consultar_telemetria

    def _resolver_planta(self, planta_id: str, organizacion_id: str | None) -> Planta:
        planta = self.repo_organizaciones.obtener_planta_por_id(planta_id)
        if planta is None or (organizacion_id is not None and planta.organizacion_id != organizacion_id):
            raise PlantaNoEncontradaError(f"Planta {planta_id} no encontrada")
        return planta

    def _resolver_nodo(
        self, planta_id: str, nodo_id: str, organizacion_id: str | None
    ) -> tuple[NodoUnifilar, list[str]]:
        planta = self._resolver_planta(planta_id, organizacion_id)
        arbol = ArbolUnifilarService(self.repo_organizaciones.obtener_nodos_unifilar(planta.id))
        return arbol.obtener(nodo_id), arbol.medidores_frontera(nodo_id)

    def _calcular_compensacion_historica(
        self, nodo: NodoUnifilar, dispositivos_ids: list[str], periodo_dias: int = 7
    ) -> CompensacionHistoricaDTO | None:
        es_acometida_mt = nodo.tipo == TipoNodoUnifilar.ACOMETIDA and nodo.tension_nominal_v >= 1000.0
        es_total_planta = nodo.device_id is None and nodo.parent_id is None

        if not (es_acometida_mt or es_total_planta):
            return None

        puntos = calcular_historico(
            dispositivos_ids=dispositivos_ids,
            consultar_telemetria=self.consultar_telemetria,
            granularidad="5m",
            horas=periodo_dias * 24,
        )

        q_kvar_vals = [
            p.potencia_reactiva_total_var / 1000.0 for p in puntos if p.potencia_reactiva_total_var is not None
        ]
        fp_vals = [p.factor_desplazamiento_total for p in puntos if p.factor_desplazamiento_total is not None]
        p_kw_vals = [p.potencia_activa_total_w / 1000.0 for p in puntos if p.potencia_activa_total_w is not None]

        if not q_kvar_vals:
            return CompensacionHistoricaDTO(
                periodo_dias=periodo_dias,
                fecha_calculo=datetime.now(timezone.utc),
                potencia_reactiva_promedio_kvar=None,
                potencia_reactiva_max_kvar=None,
                potencia_reactiva_min_kvar=None,
                factor_potencia_promedio=None,
                banco_recomendado=None,
                sobrecompensacion_sostenida=False,
            )

        q_prom = sum(q_kvar_vals) / len(q_kvar_vals)
        q_max = max(q_kvar_vals)
        q_min = min(q_kvar_vals)
        fp_prom = (sum(fp_vals) / len(fp_vals)) if fp_vals else None
        p_prom_kw = (sum(p_kw_vals) / len(p_kw_vals)) if p_kw_vals else None

        sobrecompensacion_sostenida = q_max <= 0.0

        banco: BancoRecomendadoDTO | None = None
        if p_prom_kw is not None and fp_prom is not None:
            qc_calc = DimensionadorCompensacionService.calcular_potencia_compensacion(
                potencia_activa_kw=p_prom_kw,
                fp_actual=fp_prom,
                q_reactiva_kvar=q_prom,
            )
            if qc_calc is not None and qc_calc > 0.0:
                qc_sugerida = DimensionadorCompensacionService.sugerir_banco_comercial(qc_calc)
                if qc_sugerida is not None:
                    tension_v = nodo.tension_nominal_v if nodo.tension_nominal_v >= 1000.0 else 13200.0
                    banco = BancoRecomendadoDTO(
                        tipo="banco",
                        potencia_kvar=qc_sugerida,
                        tension_instalacion_v=tension_v,
                        justificacion=f"Compensación recomendada: Q_prom={q_prom:.2f} kVAr, FP_prom={fp_prom:.3f}",
                    )

        return CompensacionHistoricaDTO(
            periodo_dias=periodo_dias,
            fecha_calculo=datetime.now(timezone.utc),
            potencia_reactiva_promedio_kvar=round(q_prom, 2),
            potencia_reactiva_max_kvar=round(q_max, 2),
            potencia_reactiva_min_kvar=round(q_min, 2),
            factor_potencia_promedio=round(fp_prom, 3) if fp_prom is not None else None,
            banco_recomendado=banco,
            sobrecompensacion_sostenida=sobrecompensacion_sostenida,
        )

    def resumen(
        self,
        planta_id: str,
        nodo_id: str,
        organizacion_id: str | None = None,
        granularidad: str = "day",
        zona: str = "America/Argentina/Buenos_Aires",
        dias: int | None = None,
    ) -> ResumenNodoUnifilarDTO:
        nodo, dispositivos_ids = self._resolver_nodo(planta_id, nodo_id, organizacion_id)
        relacion_tension_kv = nodo.metadatos_placa.relacion_tension_kv if nodo.metadatos_placa else None

        potencia_sumada, energia_sumada = calcular_resumen(
            dispositivos_ids,
            self.repo_telemetria,
            self.consultar_telemetria,
            granularidad,
            zona,
            dias,
            relacion_tension_kv,
        )

        compensacion_hist = self._calcular_compensacion_historica(nodo, dispositivos_ids, periodo_dias=7)

        return ResumenNodoUnifilarDTO(
            planta_id=planta_id,
            nodo_id=nodo.id,
            es_virtual=nodo.device_id is None,
            dispositivos_ids=dispositivos_ids,
            potencia_activa_total_w=potencia_sumada.potencia_activa_total_w,
            potencia_reactiva_total_var=potencia_sumada.potencia_reactiva_total_var,
            potencia_aparente_total_va=potencia_sumada.potencia_aparente_total_va,
            factor_desplazamiento_total=potencia_sumada.factor_desplazamiento_total,
            dispositivos_sin_dato=potencia_sumada.dispositivos_sin_dato,
            registrado_en=potencia_sumada.registrado_en,
            agregado_por_fase=_mapear_agregado_por_fase(potencia_sumada.agregado_por_fase),
            energia_agregada=[
                EnergiaAgregadaDTO(periodo=e.periodo, energia_activa_neta_kwh=e.energia_activa_neta_kwh)
                for e in energia_sumada
            ],
            compensacion_historica=compensacion_hist,
        )

    def historico(
        self,
        planta_id: str,
        nodo_id: str,
        organizacion_id: str | None = None,
        granularidad: str = "5m",
        horas: int = 24,
    ) -> list[PuntoPotenciaNodoUnifilarDTO]:
        _, dispositivos_ids = self._resolver_nodo(planta_id, nodo_id, organizacion_id)

        puntos = calcular_historico(dispositivos_ids, self.consultar_telemetria, granularidad, horas)
        return [
            PuntoPotenciaNodoUnifilarDTO(
                momento=p.momento,
                potencia_activa_total_w=p.potencia_activa_total_w,
                potencia_reactiva_total_var=p.potencia_reactiva_total_var,
                potencia_aparente_total_va=p.potencia_aparente_total_va,
                factor_desplazamiento_total=p.factor_desplazamiento_total,
                dispositivos_sin_dato=p.dispositivos_sin_dato,
            )
            for p in puntos
        ]
