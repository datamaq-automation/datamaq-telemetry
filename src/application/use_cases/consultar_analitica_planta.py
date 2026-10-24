# src/application/use_cases/consultar_analitica_planta.py
from datetime import datetime, timezone

from src.application.dtos.analitica_dto import (
    AnaliticaBancoCapacitoresPlantaDTO,
    AnaliticaPenalizacionesPlantaDTO,
)
from src.application.use_cases.agregacion_dispositivos import calcular_historico
from src.application.use_cases.consultar_telemetria import ConsultarTelemetriaUseCase
from src.domain.telemetria.analizador_reactiva import (
    DimensionadorCompensacionService,
)
from src.domain.telemetria.penalizacion_periodo import calcular_penalizacion_periodo
from src.domain.telemetria.ports import RepositorioOrganizacionesPort

# Límite de FP por debajo del cual un intervalo cuenta como penalizable (mismo valor que el DTO)
_FP_LIMITE_PENALIZACION = 0.95


class ConsultarAnaliticaPlantaUseCase:
    """Caso de uso SSOT para el cálculo de analítica reactiva y penalizaciones a nivel de planta."""

    def __init__(
        self,
        consultar_telemetria: ConsultarTelemetriaUseCase,
        repo_organizaciones: RepositorioOrganizacionesPort | None = None,
    ):
        """Args:
        consultar_telemetria: ConsultarTelemetriaUseCase para extraer histórico.
        repo_organizaciones: RepositorioOrganizacionesPort para resolver dispositivos de la planta.
        """
        self.consultar_telemetria = consultar_telemetria
        self.repo_organizaciones = repo_organizaciones

    @staticmethod
    def _extraer_series_p_q_fp(puntos: list) -> tuple[list[float], list[float], list[float]]:
        """Extrae series de P, Q, FP del histórico de telemetría."""
        q_kvar_vals = [
            p.potencia_reactiva_total_var / 1000.0 for p in puntos if p.potencia_reactiva_total_var is not None
        ]
        fp_vals = [p.factor_desplazamiento_total for p in puntos if p.factor_desplazamiento_total is not None]
        p_kw_vals = [p.potencia_activa_total_w / 1000.0 for p in puntos if p.potencia_activa_total_w is not None]
        return p_kw_vals, q_kvar_vals, fp_vals

    @staticmethod
    def _calcular_banco_sugerido(
        p_prom: float, fp_prom: float | None, q_prom: float, fp_objetivo: float = 0.96
    ) -> tuple[float | None, float | None, list[float]]:
        """Dimensiona banco de capacitores y sus escalones."""
        qc_calc = DimensionadorCompensacionService.calcular_potencia_compensacion(
            potencia_activa_kw=p_prom, fp_actual=fp_prom, fp_objetivo=fp_objetivo, q_reactiva_kvar=q_prom
        )
        banco_sugerido, escalones = None, []
        if qc_calc is not None and qc_calc > 0.0:
            banco_sugerido = DimensionadorCompensacionService.sugerir_banco_comercial(qc_calc)
            if banco_sugerido is not None:
                escalones = DimensionadorCompensacionService.calcular_escalones_sugeridos(qc_calc)
        return qc_calc, banco_sugerido, escalones

    def _resolver_dispositivos(self, planta_id: str, dispositivos_ids: list[str] | None) -> list[str]:
        """Resuelve lista de IDs de dispositivos a través del repositorio declarativo si no se proveyeron."""
        disps = list(dispositivos_ids) if dispositivos_ids else []
        if not disps and self.repo_organizaciones is not None:
            dispositivos_layout = self.repo_organizaciones.obtener_dispositivos_layout(planta_id)
            disps = [d.device_id for d in dispositivos_layout if d.device_id]
            if not disps:
                nodos = self.repo_organizaciones.obtener_nodos_unifilar(planta_id)
                disps = [n.device_id for n in nodos if n.device_id]
        return disps

    @staticmethod
    def _construir_dto_sin_datos(
        planta_id: str, periodo_dias: int, periodo_dias_orig: int
    ) -> AnaliticaBancoCapacitoresPlantaDTO:
        return AnaliticaBancoCapacitoresPlantaDTO(
            planta_id=planta_id,
            periodo_dias=periodo_dias,
            periodo_dias_analizado=periodo_dias,
            potencia_activa_promedio_kw=None,
            potencia_reactiva_promedio_kvar=None,
            potencia_reactiva_max_kvar=None,
            fp_promedio=None,
            qc_necesaria_kvar=None,
            banco_comercial_sugerido_kvar=None,
            escalones_sugeridos_kvar=[],
            sobrecompensacion_sostenida=False,
            razon_no_recomendacion=None,
            pendiente_30_dias=(periodo_dias_orig < 30),
            fecha_calculo=datetime.now(timezone.utc),
        )

    def obtener_banco_capacitores(
        self, planta_id: str, dispositivos_ids: list[str] | None = None, periodo_dias: int = 30
    ) -> AnaliticaBancoCapacitoresPlantaDTO:
        """Calcula recomendación de banco de capacitores basado en histórico real."""
        periodo_dias_orig = periodo_dias
        periodo_dias = max(7, min(60, periodo_dias))  # Validar rango [7, 60]
        disps = self._resolver_dispositivos(planta_id, dispositivos_ids)

        puntos = calcular_historico(
            dispositivos_ids=disps,
            consultar_telemetria=self.consultar_telemetria,
            granularidad="5m",
            horas=periodo_dias * 24,
        )

        p_kw_vals, q_kvar_vals, fp_vals = self._extraer_series_p_q_fp(puntos)
        if not q_kvar_vals or not p_kw_vals or not fp_vals:
            return self._construir_dto_sin_datos(planta_id, periodo_dias, periodo_dias_orig)

        p_prom = sum(p_kw_vals) / len(p_kw_vals)
        q_prom = sum(q_kvar_vals) / len(q_kvar_vals)
        q_max = max(q_kvar_vals)
        fp_prom = (sum(fp_vals) / len(fp_vals)) if fp_vals else None
        fp_objetivo = 0.96

        qc_calc, banco_sugerido, escalones = self._calcular_banco_sugerido(p_prom, fp_prom, q_prom, fp_objetivo)

        sobrecompensacion = DimensionadorCompensacionService.es_sobrecompensacion_sostenida(q_max)
        razon_no_recomendacion = None
        if sobrecompensacion:
            banco_sugerido = None
            escalones = []
            razon_no_recomendacion = "Sobrecompensación reactiva sostenida (régimen capacitivo)"
        elif fp_prom is not None and fp_prom > 0.95:
            banco_sugerido = None
            escalones = []
            razon_no_recomendacion = "Factor de potencia superior a 0.95 (sin penalización ENRE)"

        return AnaliticaBancoCapacitoresPlantaDTO(
            planta_id=planta_id,
            periodo_dias=periodo_dias,
            periodo_dias_analizado=periodo_dias,
            potencia_activa_promedio_kw=round(p_prom, 2) if p_prom is not None else None,
            potencia_reactiva_promedio_kvar=round(q_prom, 2) if q_prom is not None else None,
            potencia_reactiva_max_kvar=round(q_max, 2) if q_max is not None else None,
            fp_promedio=round(fp_prom, 3) if fp_prom is not None else None,
            fp_objetivo=fp_objetivo,
            qc_necesaria_kvar=round(qc_calc, 2) if qc_calc is not None else None,
            banco_comercial_sugerido_kvar=round(banco_sugerido, 2) if banco_sugerido is not None else None,
            escalones_sugeridos_kvar=escalones,
            sobrecompensacion_sostenida=sobrecompensacion,
            razon_no_recomendacion=razon_no_recomendacion,
            pendiente_30_dias=(periodo_dias_orig < 30),
            fecha_calculo=datetime.now(timezone.utc),
        )

    def obtener_penalizaciones(
        self,
        planta_id: str,
        periodo_dias: int = 7,
        periodo_facturacion: str | None = None,
    ) -> AnaliticaPenalizacionesPlantaDTO:
        """Con periodo_facturacion, la cifra sale de la factura de ese período (sin telemetría).
        Sin él, mantiene el análisis por ventana de bajo FP de abajo."""
        if periodo_facturacion is not None:
            return self._penalizacion_por_periodo(planta_id, periodo_facturacion)
        return self._penalizacion_por_ventana(planta_id, periodo_dias)

    @staticmethod
    def _penalizacion_por_periodo(planta_id: str, periodo_facturacion: str) -> AnaliticaPenalizacionesPlantaDTO:
        penalizacion = calcular_penalizacion_periodo(planta_id, periodo_facturacion)
        importe = penalizacion.importe_ars
        return AnaliticaPenalizacionesPlantaDTO(
            planta_id=planta_id,
            disponible=importe is not None,
            motivo_no_disponible=penalizacion.motivo_sin_precio,
            penalizacion_estimada_ars=float(importe) if importe is not None else None,
            periodo_facturacion=periodo_facturacion,
            distribuidora=penalizacion.distribuidora,
            tarifa=penalizacion.tarifa,
            fuente_archivo=penalizacion.fuente_archivo,
            concepto=penalizacion.concepto,
            timestamp_calculo=datetime.now(timezone.utc),
        )

    def _penalizacion_por_ventana(self, planta_id: str, periodo_dias: int) -> AnaliticaPenalizacionesPlantaDTO:
        """Intervalos y horas bajo FP reales por planta. La penalización en ARS queda sin calcular.

        Antes devolvía constantes fijas (P=120 kW, FP=0.88, 14,5 h) iguales para toda planta.
        Ahora cuenta buckets reales de la serie sumada de la planta. La tarifa no se inventa: sin
        tarifa de la distribuidora, penalizacion_estimada_ars queda None.
        """
        periodo_dias = max(1, min(30, periodo_dias))
        horas = periodo_dias * 24
        ahora = datetime.now(timezone.utc)
        disps = self._resolver_dispositivos(planta_id, None)
        puntos = (
            calcular_historico(
                dispositivos_ids=disps,
                consultar_telemetria=self.consultar_telemetria,
                granularidad="5m",
                horas=horas,
            )
            if disps
            else []
        )
        fp_vals = [p.factor_desplazamiento_total for p in puntos if p.factor_desplazamiento_total is not None]
        if not fp_vals:
            return AnaliticaPenalizacionesPlantaDTO(
                planta_id=planta_id,
                periodo_dias=periodo_dias,
                disponible=False,
                motivo_no_disponible="Sin registros de telemetría con FP en el período",
                timestamp_calculo=ahora,
            )
        intervalo_h = ConsultarTelemetriaUseCase._resolver_intervalo_segundos("5m", horas) / 3600.0
        intervalos_bajo = sum(1 for fp in fp_vals if fp < _FP_LIMITE_PENALIZACION)
        return AnaliticaPenalizacionesPlantaDTO(
            planta_id=planta_id,
            periodo_dias=periodo_dias,
            disponible=True,
            motivo_no_disponible=(
                "Penalización en ARS no calculada: falta la tarifa de la distribuidora de esta planta"
            ),
            intervalos_bajo_fp_count=intervalos_bajo,
            horas_bajo_fp=round(intervalos_bajo * intervalo_h, 2),
            penalizacion_estimada_ars=None,
            timestamp_calculo=ahora,
        )
