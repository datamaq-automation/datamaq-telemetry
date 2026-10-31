"""src/application/use_cases/consultar_nodo_unifilar.py."""

from datetime import datetime, timezone

import structlog

from src.application.dtos.planta_estructura_dto import (
    AgregadoPorFaseDTO,
    BancoRecomendadoDTO,
    CompensacionHistoricaDTO,
    FaseAgregadaDTO,
    HistoricoNodoUnifilarDTO,
    PuntoPotenciaNodoUnifilarDTO,
    ResumenNodoUnifilarDTO,
)
from src.application.dtos.telemetria_dto import EnergiaAgregadaDTO
from src.application.use_cases.agregacion_dispositivos import (
    calcular_datos_desde,
    calcular_demanda_cuartohoraria,
    calcular_historico,
    calcular_potencia_referencia,
    calcular_resumen,
)
from src.application.use_cases.consultar_telemetria import ConsultarTelemetriaUseCase
from src.domain.telemetria.analizador_reactiva import DimensionadorCompensacionService
from src.domain.telemetria.entities import EnergiaAgregada, NodoUnifilar, Planta
from src.domain.telemetria.exceptions import PlantaNoEncontradaError
from src.domain.telemetria.ports import RepositorioOrganizacionesPort, RepositorioTelemetriaPort
from src.domain.telemetria.servicios.agregador_dispositivos import AgregadoPorFase, PotenciaSumada
from src.domain.telemetria.servicios.arbol_unifilar import ArbolUnifilarService
from src.domain.telemetria.servicios.clasificador_nivel_tension import (
    NivelTension,
    clasificar_nivel_tension,
    tension_nominal_de_fase_v,
)
from src.domain.telemetria.servicios.relacion_transformacion import derivar_relacion_transformacion
from src.domain.telemetria.servicios.tensiones_de_linea import magnitud_tension_canonica
from src.domain.telemetria.value_objects import TipoNodoUnifilar

_log = structlog.get_logger(__name__)


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
        tension_linea_rs_V=ag.tension_linea_rs_V,
        tension_linea_st_V=ag.tension_linea_st_V,
        tension_linea_tr_V=ag.tension_linea_tr_V,
    )


def _construir_resumen_nodo_dto(
    planta_id: str,
    nodo: NodoUnifilar,
    nivel: NivelTension,
    dispositivos_ids: list[str],
    potencia_sumada: PotenciaSumada,
    energia_sumada: list[EnergiaAgregada],
    compensacion_hist: CompensacionHistoricaDTO | None,
    triada: tuple[float | None, float | None, float | None, float | None, float | None, float | None],
) -> ResumenNodoUnifilarDTO:
    (
        pot_contratada_punta,
        pot_contratada_fp,
        adquirida_curso_punta,
        adquirida_curso_fp,
        ultima_adquirida_punta,
        ultima_adquirida_fp,
    ) = triada

    return ResumenNodoUnifilarDTO(
        planta_id=planta_id,
        nodo_id=nodo.id,
        es_virtual=nodo.device_id is None,
        nivel_tension=nivel,
        tension_nominal_V=nodo.tension_nominal_v,
        tension_nominal_fase_V=tension_nominal_de_fase_v(nodo.tension_nominal_v),
        magnitud_tension_canonica=magnitud_tension_canonica(nivel),
        dispositivos_ids=dispositivos_ids,
        potencia_activa_total_w=potencia_sumada.potencia_activa_total_w,
        potencia_reactiva_total_var=potencia_sumada.potencia_reactiva_total_var,
        potencia_aparente_total_va=potencia_sumada.potencia_aparente_total_va,
        factor_desplazamiento_total=potencia_sumada.factor_desplazamiento_total,
        dispositivos_sin_dato=potencia_sumada.dispositivos_sin_dato,
        registrado_en=potencia_sumada.registrado_en,
        agregado_por_fase=_mapear_agregado_por_fase(potencia_sumada.agregado_por_fase),
        energia_agregada=[
            EnergiaAgregadaDTO(
                periodo=e.periodo,
                energia_activa_neta_kwh=e.energia_activa_neta_kwh,
                periodos_sin_datos_previos=e.periodos_sin_datos_previos,
            )
            for e in energia_sumada
        ],
        compensacion_historica=compensacion_hist,
        potencia_contratada_punta_kw=pot_contratada_punta,
        potencia_contratada_fuera_punta_kw=pot_contratada_fp,
        potencia_adquirida_punta_en_curso_kw=adquirida_curso_punta,
        potencia_adquirida_fuera_punta_en_curso_kw=adquirida_curso_fp,
        ultima_potencia_adquirida_punta_kw=ultima_adquirida_punta,
        ultima_potencia_adquirida_fuera_punta_kw=ultima_adquirida_fp,
    )


class ConsultarNodoUnifilarUseCase:
    """Telemetría agregada de un nodo del unifilar: suma de sus medidores frontera."""

    def __init__(
        self,
        repo_organizaciones: RepositorioOrganizacionesPort,
        repo_telemetria: RepositorioTelemetriaPort,
        consultar_telemetria: ConsultarTelemetriaUseCase,
    ) -> None:
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
    ) -> tuple[NodoUnifilar, list[NodoUnifilar]]:
        """Devuelve el nodo consultado y los nodos de su frontera de medición.

        Los nodos frontera (no sólo sus `device_id`) hacen falta para derivar la
        relación de transformación: es su tensión nominal la que fija la escala
        desde la que se proyecta el agregado.
        """
        planta = self._resolver_planta(planta_id, organizacion_id)
        arbol = ArbolUnifilarService(self.repo_organizaciones.obtener_nodos_unifilar(planta.id))
        return arbol.obtener(nodo_id), arbol.nodos_medidores_frontera(nodo_id)

    def _calcular_compensacion_historica(
        self, nodo: NodoUnifilar, dispositivos_ids: list[str], periodo_dias: int = 30
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

    def _resolver_triada_potencia(
        self,
        planta_id: str,
        nodo: NodoUnifilar,
        dispositivos_ids: list[str],
        zona: str,
    ) -> tuple[float | None, float | None, float | None, float | None, float | None, float | None]:
        facturas = self.repo_organizaciones.obtener_facturas_planta(planta_id)
        factura_reciente = facturas[0] if facturas else None

        if nodo.potencia_contratada_punta_kw is not None or nodo.potencia_contratada_fuera_punta_kw is not None:
            pot_contratada_punta = nodo.potencia_contratada_punta_kw
            pot_contratada_fp = nodo.potencia_contratada_fuera_punta_kw
        elif nodo.tipo == TipoNodoUnifilar.ACOMETIDA or nodo.parent_id is None:
            pot_contratada_punta = factura_reciente.potencia_contratada_punta_kw if factura_reciente else None
            pot_contratada_fp = factura_reciente.potencia_contratada_fuera_punta_kw if factura_reciente else None
        else:
            pot_contratada_punta = None
            pot_contratada_fp = None

        if nodo.tipo == TipoNodoUnifilar.ACOMETIDA or nodo.parent_id is None:
            ultima_adquirida_punta = factura_reciente.potencia_adquirida_punta_kw if factura_reciente else None
            ultima_adquirida_fp = factura_reciente.potencia_adquirida_fuera_punta_kw if factura_reciente else None
        else:
            ultima_adquirida_punta = None
            ultima_adquirida_fp = None

        if dispositivos_ids and (nodo.tipo == TipoNodoUnifilar.ACOMETIDA or nodo.parent_id is None):
            demanda_curso = calcular_demanda_cuartohoraria(
                dispositivos_ids,
                self.consultar_telemetria,
                zona=zona,
            )
            adquirida_curso_punta = demanda_curso.potencia_adquirida_punta_kw
            adquirida_curso_fp = demanda_curso.potencia_adquirida_fuera_punta_kw
        else:
            adquirida_curso_punta = None
            adquirida_curso_fp = None

        return (
            pot_contratada_punta,
            pot_contratada_fp,
            adquirida_curso_punta,
            adquirida_curso_fp,
            ultima_adquirida_punta,
            ultima_adquirida_fp,
        )

    def resumen(
        self,
        planta_id: str,
        nodo_id: str,
        organizacion_id: str | None = None,
        granularidad: str = "day",
        zona: str = "America/Argentina/Buenos_Aires",
        dias: int | None = None,
        periodo_dias: int | None = None,
    ) -> ResumenNodoUnifilarDTO:
        nodo, nodos_frontera = self._resolver_nodo(planta_id, nodo_id, organizacion_id)
        dispositivos_ids = [n.device_id for n in nodos_frontera if n.device_id]

        _log.info(
            "nodo_unifilar_frontera_resuelta",
            planta_id=planta_id,
            nodo_id=nodo_id,
            nodos_frontera_count=len(nodos_frontera),
            dispositivos_ids=dispositivos_ids,
            dispositivos_unicos=len(set(dispositivos_ids)),
            hay_duplicados=len(dispositivos_ids) != len(set(dispositivos_ids)),
        )

        nivel = clasificar_nivel_tension(nodo.tension_nominal_v)

        relacion = derivar_relacion_transformacion(nodo, nodos_frontera)
        if relacion.advertencia is not None:
            _log.warning(
                "unifilar_relacion_transformacion_degradada",
                planta_id=planta_id,
                nodo_id=nodo.id,
                origen=relacion.origen,
                factor=relacion.factor,
                motivo=relacion.advertencia,
            )

        potencia_sumada, energia_sumada = calcular_resumen(
            dispositivos_ids,
            self.repo_telemetria,
            self.consultar_telemetria,
            granularidad,
            zona,
            dias,
            relacion.factor,
        )

        # Usar periodo_dias si se especifica, sino dias, sino default de 30 (ISO 50001)
        periodo_dias_comp = periodo_dias if periodo_dias is not None else (dias if dias is not None else 30)
        compensacion_hist = self._calcular_compensacion_historica(
            nodo, dispositivos_ids, periodo_dias=periodo_dias_comp
        )

        triada = self._resolver_triada_potencia(planta_id, nodo, dispositivos_ids, zona)

        return _construir_resumen_nodo_dto(
            planta_id=planta_id,
            nodo=nodo,
            nivel=nivel,
            dispositivos_ids=dispositivos_ids,
            potencia_sumada=potencia_sumada,
            energia_sumada=energia_sumada,
            compensacion_hist=compensacion_hist,
            triada=triada,
        )

    def historico(
        self,
        planta_id: str,
        nodo_id: str,
        organizacion_id: str | None = None,
        granularidad: str = "5m",
        horas: int = 24,
        hasta: datetime | None = None,
    ) -> HistoricoNodoUnifilarDTO:
        _, nodos_frontera = self._resolver_nodo(planta_id, nodo_id, organizacion_id)
        dispositivos_ids = [n.device_id for n in nodos_frontera if n.device_id]

        _log.info(
            "nodo_unifilar_frontera_resuelta",
            planta_id=planta_id,
            nodo_id=nodo_id,
            nodos_frontera_count=len(nodos_frontera),
            dispositivos_ids=dispositivos_ids,
            dispositivos_unicos=len(set(dispositivos_ids)),
            hay_duplicados=len(dispositivos_ids) != len(set(dispositivos_ids)),
        )

        datos_desde = calcular_datos_desde(dispositivos_ids, self.consultar_telemetria)
        puntos = calcular_historico(dispositivos_ids, self.consultar_telemetria, granularidad, horas, hasta)
        if datos_desde is not None:
            # Antes del corte más reciente falta al menos un medidor: la suma estaría incompleta.
            puntos = [p for p in puntos if p.momento >= datos_desde]
        return HistoricoNodoUnifilarDTO(
            puntos=[
                PuntoPotenciaNodoUnifilarDTO(
                    momento=p.momento,
                    potencia_activa_total_w=p.potencia_activa_total_w,
                    potencia_reactiva_total_var=p.potencia_reactiva_total_var,
                    potencia_aparente_total_va=p.potencia_aparente_total_va,
                    factor_desplazamiento_total=p.factor_desplazamiento_total,
                    dispositivos_sin_dato=p.dispositivos_sin_dato,
                    dispositivos_interpolados=p.dispositivos_interpolados,
                )
                for p in puntos
            ],
            datos_desde=datos_desde,
        )

    def potencia_referencia(self, planta_id: str, nodo_id: str, organizacion_id: str | None = None) -> float | None:
        """P99 de la serie sumada de los medidores frontera en los últimos 30 días (D1, D2);
        independiente de la ventana consultada. ``None`` sin medidores o sin datos suficientes."""
        _, nodos_frontera = self._resolver_nodo(planta_id, nodo_id, organizacion_id)
        dispositivos_ids = [n.device_id for n in nodos_frontera if n.device_id]
        return calcular_potencia_referencia(dispositivos_ids, self.consultar_telemetria)
