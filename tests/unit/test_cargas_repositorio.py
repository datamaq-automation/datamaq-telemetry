"""Repositorio SQLAlchemy del catálogo de cargas, con SQLite en memoria."""

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from itertools import count

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from src.domain.cargas.entities import Carga, IntervaloActividadCarga
from src.domain.cargas.value_objects import (
    CategoriaCarga,
    EstadoCampana,
    FirmaCarga,
    MuestraCampana,
    NaturalezaElectrica,
    OrigenClasificacionCarga,
    OrigenFirma,
    PatronOperacion,
    TipoCampana,
)
from src.infrastructure.sqlalchemy.models import Base, TelemetryInstantaneousModel
from src.infrastructure.sqlalchemy.models_cargas import (
    CampaignSampleModel,
    LoadActivityIntervalModel,
)
from src.infrastructure.sqlalchemy.repositories.campanas_repository import MySQLCampanasRepository
from src.infrastructure.sqlalchemy.repositories.cargas_repository import (
    MySQLCargasRepository,
    MySQLSeriePotenciaRepository,
)
from src.infrastructure.sqlalchemy.repositories.intervalos_repository import (
    MySQLIntervalosActividadRepository,
)

MEDIDOR_CASA = "dev-casa"
OTRO_MEDIDOR = "dev-taller"
MEDIDO_EN = datetime(2026, 9, 4, 3, 0, 0, tzinfo=timezone.utc)
_CONTADOR_PK = count(1)


def _asignar_pk_auto(session: Session, flush_context, instances) -> None:
    """SQLite no autoincrementa un PK `BigInteger`; MySQL sí.

    Mismo apaño que `tests/unit/test_mysql_repositories.py`: es una limitación del motor
    de test, no del modelo.
    """
    for obj in session.new:
        if (
            isinstance(obj, (CampaignSampleModel, LoadActivityIntervalModel, TelemetryInstantaneousModel))
            and obj.id is None
        ):
            obj.id = next(_CONTADOR_PK)


@pytest.fixture()
def db() -> Iterator[Session]:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    event.listen(session, "before_flush", _asignar_pk_auto)
    try:
        yield session
    finally:
        session.close()


def _carga(carga_id: str = "carga-1", nombre: str = "Heladera", **kwargs) -> Carga:
    base: dict = dict(
        dispositivo_id=MEDIDOR_CASA,
        categoria=CategoriaCarga.REFRIGERACION,
        naturaleza_electrica=NaturalezaElectrica.MOTOR,
        potencia_nominal_w=120.0,
    )
    base.update(kwargs)
    return Carga(id=carga_id, nombre=nombre, **base)


def _firma_completa() -> FirmaCarga:
    return FirmaCarga(
        potencia_w=118.5,
        dispersion_w=9.25,
        potencia_reactiva_var=95.0,
        factor_potencia=0.781,
        duracion_encendido_s=1320.0,
        duracion_encendido_mad_s=180.0,
        duracion_apagado_s=2400.0,
        pico_arranque_w=640.0,
        origen=OrigenFirma.CAMPANA,
        muestras=1440,
        medida_en=MEDIDO_EN,
    )


def test_guardar_y_recuperar_carga_sin_firma(db: Session) -> None:
    repo = MySQLCargasRepository(db)

    repo.guardar(_carga())
    obtenida = repo.obtener_por_id("carga-1")

    assert obtenida is not None
    assert obtenida.nombre == "Heladera"
    assert obtenida.categoria == CategoriaCarga.REFRIGERACION
    assert obtenida.naturaleza_electrica == NaturalezaElectrica.MOTOR
    assert obtenida.patron_operacion == PatronOperacion.INDETERMINADO
    assert obtenida.potencia_nominal_w == 120.0
    assert obtenida.firma is None
    assert obtenida.esta_caracterizada is False


def test_la_firma_sobrevive_al_viaje_de_ida_y_vuelta(db: Session) -> None:
    """Numeric↔float no debe perder ninguno de los campos de la firma."""
    repo = MySQLCargasRepository(db)

    repo.guardar(_carga(firma=_firma_completa()))
    firma = repo.obtener_por_id("carga-1").firma

    assert firma is not None
    assert firma.potencia_w == 118.5
    assert firma.dispersion_w == 9.25
    assert firma.potencia_reactiva_var == 95.0
    assert firma.factor_potencia == 0.781
    assert firma.duracion_encendido_s == 1320.0
    assert firma.duracion_encendido_mad_s == 180.0
    assert firma.duracion_apagado_s == 2400.0
    assert firma.pico_arranque_w == 640.0
    assert firma.origen == OrigenFirma.CAMPANA
    assert firma.muestras == 1440
    assert firma.esta_completa is True


def test_guardar_dos_veces_el_mismo_id_actualiza_en_lugar_de_duplicar(db: Session) -> None:
    repo = MySQLCargasRepository(db)
    repo.guardar(_carga())

    carga = repo.obtener_por_id("carga-1")
    carga.nombre = "Heladera de la cocina"
    carga.patron_operacion = PatronOperacion.CICLICO_TERMOSTATICO
    repo.guardar(carga)

    assert len(repo.listar()) == 1
    assert repo.obtener_por_id("carga-1").nombre == "Heladera de la cocina"
    assert repo.obtener_por_id("carga-1").patron_operacion == PatronOperacion.CICLICO_TERMOSTATICO


def test_quitar_la_firma_limpia_todas_sus_columnas(db: Session) -> None:
    """Recalibrar desde cero no debe dejar restos de la firma anterior."""
    repo = MySQLCargasRepository(db)
    repo.guardar(_carga(firma=_firma_completa()))

    carga = repo.obtener_por_id("carga-1")
    carga.firma = None
    repo.guardar(carga)

    assert repo.obtener_por_id("carga-1").firma is None


def test_obtener_por_nombre_esta_acotado_al_medidor(db: Session) -> None:
    repo = MySQLCargasRepository(db)
    repo.guardar(_carga("carga-1", "Heladera"))
    repo.guardar(_carga("carga-2", "Heladera", dispositivo_id=OTRO_MEDIDOR))

    assert repo.obtener_por_nombre(MEDIDOR_CASA, "Heladera").id == "carga-1"
    assert repo.obtener_por_nombre(OTRO_MEDIDOR, "Heladera").id == "carga-2"
    assert repo.obtener_por_nombre(MEDIDOR_CASA, "Freezer") is None


def test_listar_por_dispositivo_ordena_por_nombre_y_filtra_inactivas(db: Session) -> None:
    repo = MySQLCargasRepository(db)
    repo.guardar(_carga("c1", "Termotanque"))
    repo.guardar(_carga("c2", "Anafe eléctrico", activa=False))
    repo.guardar(_carga("c3", "Heladera"))
    repo.guardar(_carga("c4", "Horno", dispositivo_id=OTRO_MEDIDOR))

    todas = repo.listar_por_dispositivo(MEDIDOR_CASA)
    activas = repo.listar_por_dispositivo(MEDIDOR_CASA, solo_activas=True)

    assert [c.nombre for c in todas] == ["Anafe eléctrico", "Heladera", "Termotanque"]
    assert [c.nombre for c in activas] == ["Heladera", "Termotanque"]


def test_obtener_carga_inexistente_devuelve_none(db: Session) -> None:
    assert MySQLCargasRepository(db).obtener_por_id("no-existe") is None


def _instantanea(db: Session, segundos: int, p: float | None, q: float | None, fp: float | None) -> None:
    from decimal import Decimal

    from src.infrastructure.sqlalchemy.models import TelemetryInstantaneousModel

    db.add(
        TelemetryInstantaneousModel(
            id=segundos + 1,
            device_id=MEDIDOR_CASA,
            recorded_at=datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc) + timedelta(seconds=segundos),
            total_active_power=Decimal(str(p)) if p is not None else None,
            total_reactive_power=Decimal(str(q)) if q is not None else None,
            total_power_factor=Decimal(str(fp)) if fp is not None else None,
        )
    )
    db.commit()


def test_la_serie_trae_potencia_reactiva_y_factor_de_potencia(db: Session) -> None:
    """Q y FP son el eje que separa una carga resistiva de una con motor."""
    _instantanea(db, 0, 1850.0, 12.0, 0.99)

    serie = MySQLSeriePotenciaRepository(db).listar_serie_potencia(
        MEDIDOR_CASA, datetime(2026, 8, 1, tzinfo=timezone.utc)
    )

    assert len(serie) == 1
    assert serie[0].potencia_w == 1850.0
    assert serie[0].potencia_reactiva_var == 12.0
    assert serie[0].factor_potencia == 0.99


def test_la_serie_llega_ordenada_cronologicamente(db: Session) -> None:
    """Todos los servicios del contexto asumen orden temporal ascendente."""
    for segundos in (900, 0, 600, 300):
        _instantanea(db, segundos, 100.0 + segundos, None, None)

    serie = MySQLSeriePotenciaRepository(db).listar_serie_potencia(
        MEDIDOR_CASA, datetime(2026, 8, 1, tzinfo=timezone.utc)
    )

    assert [lectura.potencia_w for lectura in serie] == [100.0, 400.0, 700.0, 1000.0]


def test_las_lecturas_sin_potencia_activa_no_entran_en_la_serie(db: Session) -> None:
    """Una lectura sin P no aporta a un análisis de potencia y obligaría a filtrarla aguas abajo."""
    _instantanea(db, 0, 120.0, None, None)
    _instantanea(db, 300, None, 30.0, 0.5)

    serie = MySQLSeriePotenciaRepository(db).listar_serie_potencia(
        MEDIDOR_CASA, datetime(2026, 8, 1, tzinfo=timezone.utc)
    )

    assert len(serie) == 1


def test_la_serie_respeta_la_ventana_y_el_limite(db: Session) -> None:
    for i in range(6):
        _instantanea(db, i * 300, 100.0 * (i + 1), None, None)

    repo = MySQLSeriePotenciaRepository(db)
    base = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)

    acotada = repo.listar_serie_potencia(MEDIDOR_CASA, base + timedelta(seconds=600), base + timedelta(seconds=1200))
    limitada = repo.listar_serie_potencia(MEDIDOR_CASA, base, limite=2)

    assert [lectura.potencia_w for lectura in acotada] == [300.0, 400.0, 500.0]
    assert len(limitada) == 2


def _campana(db: Session, campana_id: str = "camp-1", tipo: TipoCampana = TipoCampana.ACTIVA):
    from src.domain.cargas.entities import CampanaCaracterizacion

    return MySQLCampanasRepository(db).guardar(
        CampanaCaracterizacion(
            id=campana_id,
            dispositivo_id=MEDIDOR_CASA,
            carga_id=None,
            tipo=tipo,
            inicio_at=MEDIDO_EN,
            fin_planificado_at=MEDIDO_EN + timedelta(minutes=5),
        )
    )


def test_la_campana_sobrevive_al_viaje_de_ida_y_vuelta(db: Session) -> None:
    repo = MySQLCampanasRepository(db)
    _campana(db)

    campana = repo.obtener_por_id("camp-1")

    assert campana is not None
    assert campana.tipo == TipoCampana.ACTIVA
    assert campana.estado == EstadoCampana.EN_CURSO
    assert campana.esta_en_curso is True
    assert campana.duracion_planificada_s == 300.0


def test_agregar_muestra_es_idempotente_ante_el_redelivery_de_qos_1(db: Session) -> None:
    """La unicidad la garantiza la restricción de la tabla, no un SELECT previo."""
    repo = MySQLCampanasRepository(db)
    _campana(db)
    muestra = MuestraCampana(momento=MEDIDO_EN, potencia_w=1850.0, potencia_reactiva_var=12.0)

    primera = repo.agregar_muestra("camp-1", muestra)
    repetida = repo.agregar_muestra("camp-1", muestra)

    assert (primera, repetida) == (True, False)
    assert len(repo.listar_muestras("camp-1")) == 1
    assert repo.obtener_por_id("camp-1").muestras == 1


def test_las_muestras_vuelven_ordenadas_y_completas(db: Session) -> None:
    repo = MySQLCampanasRepository(db)
    _campana(db)
    for segundos in (2, 0, 1):
        repo.agregar_muestra(
            "camp-1",
            MuestraCampana(
                momento=MEDIDO_EN + timedelta(seconds=segundos),
                potencia_w=100.0 * (segundos + 1),
                potencia_reactiva_var=5.0,
                factor_potencia=0.987,
                tension_v=221.6,
                corriente_a=8.4,
            ),
        )

    muestras = repo.listar_muestras("camp-1")

    assert [m.potencia_w for m in muestras] == [100.0, 200.0, 300.0]
    assert muestras[0].factor_potencia == 0.987
    assert muestras[0].tension_v == 221.6


def test_solo_se_lista_una_campana_en_curso_por_dispositivo(db: Session) -> None:
    repo = MySQLCampanasRepository(db)
    campana = _campana(db)
    assert repo.obtener_en_curso_por_dispositivo(MEDIDOR_CASA) is not None

    campana.cerrar(EstadoCampana.COMPLETADA)
    repo.guardar(campana)

    assert repo.obtener_en_curso_por_dispositivo(MEDIDOR_CASA) is None
    assert repo.listar_en_curso() == []


def _intervalo_ent(
    inicio_min: int, fin_min: int, carga_id: str | None = None, origen=OrigenClasificacionCarga.REGLA
) -> IntervaloActividadCarga:
    return IntervaloActividadCarga(
        id=None,
        dispositivo_id=MEDIDOR_CASA,
        carga_id=carga_id,
        inicio_at=MEDIDO_EN + timedelta(minutes=inicio_min),
        fin_at=MEDIDO_EN + timedelta(minutes=fin_min),
        potencia_media_w=1800.0,
        energia_kwh=0.6,
        confianza=0.82,
        origen=origen,
    )


def test_reemplazar_ventana_reescribe_en_lugar_de_acumular(db: Session) -> None:
    repo = MySQLIntervalosActividadRepository(db)
    ventana = (MEDIDOR_CASA, MEDIDO_EN, MEDIDO_EN + timedelta(hours=6))

    repo.reemplazar_ventana(*ventana, [_intervalo_ent(0, 40), _intervalo_ent(60, 100)])
    repo.reemplazar_ventana(*ventana, [_intervalo_ent(0, 40), _intervalo_ent(60, 100)])

    assert len(repo.listar_por_dispositivo(*ventana)) == 2


def test_reemplazar_ventana_preserva_las_correcciones_humanas(db: Session) -> None:
    """El batch no puede deshacer lo que una persona confirmó a mano."""
    repo = MySQLIntervalosActividadRepository(db)
    ventana = (MEDIDOR_CASA, MEDIDO_EN, MEDIDO_EN + timedelta(hours=6))
    corregido = _intervalo_ent(0, 40, carga_id="carga-1", origen=OrigenClasificacionCarga.CORRECCION_HUMANA)
    corregido.corregido_por_usuario_id = "u1"
    repo.reemplazar_ventana(*ventana, [corregido])

    escritos = repo.reemplazar_ventana(*ventana, [_intervalo_ent(0, 40, carga_id=None), _intervalo_ent(60, 100)])

    sobrevivientes = repo.listar_por_dispositivo(*ventana)
    humano = next(i for i in sobrevivientes if i.es_correccion_humana)
    assert escritos == 1
    assert len(sobrevivientes) == 2
    assert humano.carga_id == "carga-1"
    assert humano.corregido_por_usuario_id == "u1"


def test_un_intervalo_sin_carga_es_no_atribuido_y_se_guarda_igual(db: Session) -> None:
    """El residual honesto es lo que permite saber cuánto del consumo queda sin explicar."""
    repo = MySQLIntervalosActividadRepository(db)

    guardado = repo.guardar(_intervalo_ent(0, 40, carga_id=None))

    assert guardado.id is not None
    assert guardado.esta_atribuido is False
    assert guardado.energia_kwh == 0.6


def test_la_energia_del_periodo_sale_del_contador_acumulado(db: Session) -> None:
    from decimal import Decimal

    from src.infrastructure.sqlalchemy.models import TelemetryEnergyModel

    for i, kwh in enumerate(("1000.500", "1003.750")):
        db.add(
            TelemetryEnergyModel(
                id=i + 1,
                device_id=MEDIDOR_CASA,
                recorded_at=MEDIDO_EN + timedelta(hours=i),
                net_active_energy_kwh=Decimal(kwh),
            )
        )
    db.commit()

    total = MySQLSeriePotenciaRepository(db).obtener_energia_consumida_kwh(
        MEDIDOR_CASA, MEDIDO_EN, MEDIDO_EN + timedelta(days=1)
    )

    assert total == 3.25


def test_con_una_sola_lectura_del_contador_no_hay_diferencia_que_calcular(db: Session) -> None:
    """Devolver 0 se confundiría con "no consumió nada"."""
    from decimal import Decimal

    from src.infrastructure.sqlalchemy.models import TelemetryEnergyModel

    db.add(
        TelemetryEnergyModel(
            id=1, device_id=MEDIDOR_CASA, recorded_at=MEDIDO_EN, net_active_energy_kwh=Decimal("1000.5")
        )
    )
    db.commit()

    assert (
        MySQLSeriePotenciaRepository(db).obtener_energia_consumida_kwh(
            MEDIDOR_CASA, MEDIDO_EN, MEDIDO_EN + timedelta(days=1)
        )
        is None
    )
