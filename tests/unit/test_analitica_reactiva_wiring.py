"""tests/unit/test_analitica_reactiva_wiring.py — D-11: el dispositivo debe llegar al motor de analítica.

La lógica de exención tarifaria (`_evaluar_abstencion_enre`) ya estaba correcta y probada
en aislamiento (tests/unit/test_analitica_reactiva_categoria.py). El bug real era de
cableado: `TelemetriaMapper.instantanea_to_dto` y sus tres callers en la aplicación
(GET /latest, GET /instantaneous, WS /inst) nunca pasaban `dispositivo`, así que
`calcular_analitica_completa` siempre lo recibía en `None` y la exención jamás se
disparaba en un request real — un medidor T1-R/monofásico podía recibir
`requiere_compensacion: true` con un monto real en pesos.

Estos tests cubren esa integración, no la lógica de dominio.
"""

from datetime import datetime, timezone

from src.application.mappers.telemetria_mapper import TelemetriaMapper
from src.application.use_cases.consultar_telemetria import ConsultarTelemetriaUseCase
from src.domain.telemetria.entities import Dispositivo, LecturaInstantanea, MedicionFase
from src.domain.telemetria.value_objects import (
    Corriente,
    EstadoDispositivo,
    FactorPotencia,
    MacAddress,
    PotenciaActiva,
    Tension,
)
from tests.unit.test_use_cases import MockDispositivosRepo, MockTelemetriaRepo

AHORA = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)


def _lectura_fp_bajo() -> LecturaInstantanea:
    """FP 0.70, potencia suficiente para disparar compensación si no hay exención."""
    fase = MedicionFase(
        tension=Tension(220.0),
        corriente=Corriente(10.0),
        potencia_activa=PotenciaActiva(2000.0),
        factor_potencia=FactorPotencia(0.70),
    )
    return LecturaInstantanea(
        id=1,
        dispositivo_id="dev-mono",
        registrado_en=AHORA,
        fase_r=fase,
        fase_s=fase,
        fase_t=fase,
        potencia_activa_total=PotenciaActiva(6000.0),
        factor_potencia_total=FactorPotencia(0.70),
    )


def _dispositivo_monofasico_exento() -> Dispositivo:
    return Dispositivo(
        id="dev-mono",
        device_uid=MacAddress("D48C49F03564"),
        nombre="Powermeter-Mono",
        categoria_tarifaria="T1-R",
        penalizacion_reactiva_aplica=False,
        tipo_instalacion="CONSUMO",
        fases_con_ti="R",
        estado=EstadoDispositivo.ONLINE,
    )


def test_instantanea_to_dto_sin_dispositivo_no_exime_bug_original():
    """Reproduce el bug: sin `dispositivo`, la exención nunca se activa aunque la
    lectura sea de un medidor T1-R monofásico con FP bajo."""
    dto = TelemetriaMapper.instantanea_to_dto(_lectura_fp_bajo())

    assert dto.analitica is not None
    assert dto.analitica.requiere_compensacion is True
    assert dto.analitica.motivo_abstencion is None


def test_instantanea_to_dto_con_dispositivo_exime_correctamente():
    """El fix: pasando `dispositivo`, la exención tarifaria se aplica end-to-end."""
    dto = TelemetriaMapper.instantanea_to_dto(_lectura_fp_bajo(), dispositivo=_dispositivo_monofasico_exento())

    assert dto.analitica is not None
    assert dto.analitica.requiere_compensacion is False
    assert dto.analitica.penalizacion_estimada_ars is None
    assert dto.analitica.motivo_abstencion == "TARIFA_SIN_CARGO_REACTIVA"


def test_instantanea_to_dto_respeta_analitica_precomputada_aunque_haya_dispositivo():
    """Si ya viene una `analitica` calculada (p. ej. con ventana integrada, D-12),
    `dispositivo` no debe recalcularla ni pisarla."""
    from src.domain.telemetria.value_objects import AnaliticaCalidadEnergia

    analitica_previa = AnaliticaCalidadEnergia(requiere_compensacion=True, motivo_abstencion=None)
    dto = TelemetriaMapper.instantanea_to_dto(
        _lectura_fp_bajo(), analitica=analitica_previa, dispositivo=_dispositivo_monofasico_exento()
    )

    assert dto.analitica is not None
    assert dto.analitica.requiere_compensacion is True
    assert dto.analitica.motivo_abstencion is None


def test_get_latest_exime_medidor_monofasico_de_punta_a_punta():
    """D-11 de punta a punta: GET /latest (obtener_ultima_telemetria) sobre un
    dispositivo T1-R/monofásico no debe emitir requiere_compensacion=true."""
    repo_disp = MockDispositivosRepo()
    dispositivo = _dispositivo_monofasico_exento()
    repo_disp.guardar(dispositivo)

    repo_telem = MockTelemetriaRepo()
    repo_telem.instantaneas.append(_lectura_fp_bajo())

    use_case = ConsultarTelemetriaUseCase(repo_telem, repo_disp)
    resultado = use_case.obtener_ultima_telemetria(dispositivo.id)

    assert resultado.analitica is not None
    assert resultado.analitica.requiere_compensacion is False
    assert resultado.analitica.motivo_abstencion == "TARIFA_SIN_CARGO_REACTIVA"
