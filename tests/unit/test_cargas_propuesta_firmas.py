"""tests/unit/test_cargas_propuesta_firmas.py — Caso de uso: proponer firmas inferidas."""

from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from src.application.use_cases.proponer_firmas_inferidas import ProponerFirmasInferidasUseCase
from src.domain.cargas.entities import Carga
from src.domain.cargas.exceptions import DescubridorNoDisponibleError
from src.domain.cargas.ports import DescubridorCargasPort, RepositorioCargasPort
from src.domain.cargas.value_objects import CargaCandidata, FirmaCarga, OrigenFirma

DISPOSITIVO_A = "dev-001"
MEDIDOR_NAME = "Trafo arriba"


class MockCargasRepo(RepositorioCargasPort):
    """Repositorio en memoria para tests."""

    def __init__(self):
        self.cargas: dict[str, Carga] = {}

    def obtener_por_id(self, carga_id: str) -> Carga | None:
        return self.cargas.get(carga_id)

    def obtener_por_nombre(self, dispositivo_id: str, nombre: str) -> Carga | None:
        return next(
            (c for c in self.cargas.values() if c.dispositivo_id == dispositivo_id and c.nombre == nombre),
            None,
        )

    def listar_por_dispositivo(self, dispositivo_id: str, solo_activas: bool = False) -> list[Carga]:
        cargas = [c for c in self.cargas.values() if c.dispositivo_id == dispositivo_id]
        if solo_activas:
            cargas = [c for c in cargas if c.activa]
        return sorted(cargas, key=lambda c: c.nombre)

    def listar(self) -> list[Carga]:
        return sorted(self.cargas.values(), key=lambda c: c.nombre)

    def guardar(self, carga: Carga) -> Carga:
        self.cargas[carga.id] = carga
        return carga


class MockDescubridor(DescubridorCargasPort):
    """Descubridor fake para tests."""

    def __init__(self, candidatas: list[CargaCandidata] | None = None):
        self.candidatas = candidatas or []

    def descubrir(self, medidor: str, desde: datetime, hasta: datetime) -> list[CargaCandidata]:
        return self.candidatas


@pytest.fixture
def repo_vacio():
    return MockCargasRepo()


@pytest.fixture
def descubridor_con_candidatas():
    return MockDescubridor(
        candidatas=[
            CargaCandidata(
                potencia_w=90000.0,
                dispersion_w=5000.0,
                encendidos=10,
                apagados=10,
                ciclos_por_dia=2.5,
                on_off=True,
            ),
            CargaCandidata(
                potencia_w=50000.0,
                dispersion_w=2000.0,
                encendidos=5,
                apagados=5,
                ciclos_por_dia=1.0,
                on_off=True,
            ),
            CargaCandidata(
                potencia_w=92000.0,
                dispersion_w=0.0,
                encendidos=0,
                apagados=0,
                ciclos_por_dia=None,
                on_off=False,  # Será descartada
            ),
        ]
    )


def test_emparejada_con_firma_chapa_se_actualiza_a_inferida(repo_vacio, descubridor_con_candidatas):
    """Candidata 90 kW emparejada con firma CHAPA → se actualiza a INFERIDA con dispersión y muestras."""
    # Pre-cargar una carga con firma CHAPA
    carga_existente = Carga(
        id="c1",
        dispositivo_id=DISPOSITIVO_A,
        nombre="Carga 90kW",
        potencia_nominal_w=90000.0,
        firma=FirmaCarga(potencia_w=90000.0, origen=OrigenFirma.CHAPA),
    )
    repo_vacio.guardar(carga_existente)

    use_case = ProponerFirmasInferidasUseCase(repo_vacio, descubridor_con_candidatas)
    desde = datetime(2026, 1, 1, tzinfo=timezone.utc)
    hasta = datetime(2026, 1, 2, tzinfo=timezone.utc)

    resultado = use_case.execute(DISPOSITIVO_A, MEDIDOR_NAME, desde, hasta)

    assert "Carga 90kW" in resultado.actualizadas
    assert len(resultado.creadas) == 1  # La de 50 kW no emparejada
    assert len(resultado.protegidas) == 0
    assert resultado.descartadas == 1  # La on_off=False

    # Verificar que la firma se actualizó
    carga_actualizada = repo_vacio.obtener_por_id("c1")
    assert carga_actualizada is not None
    assert carga_actualizada.firma is not None
    assert carga_actualizada.firma.origen == OrigenFirma.INFERIDA
    assert carga_actualizada.firma.potencia_w == 90000.0
    assert carga_actualizada.firma.dispersion_w == 5000.0
    assert carga_actualizada.firma.muestras == 20  # encendidos + apagados


def test_emparejada_con_firma_campana_es_protegida(repo_vacio, descubridor_con_candidatas):
    """Candidata emparejada con firma CAMPANA → en protegidas, no se actualiza."""
    # Pre-cargar una carga con firma CAMPANA
    carga_campana = Carga(
        id="c1",
        dispositivo_id=DISPOSITIVO_A,
        nombre="Carga 90kW",
        potencia_nominal_w=90000.0,
        firma=FirmaCarga(potencia_w=90000.0, origen=OrigenFirma.CAMPANA),
    )
    repo_vacio.guardar(carga_campana)

    use_case = ProponerFirmasInferidasUseCase(repo_vacio, descubridor_con_candidatas)
    desde = datetime(2026, 1, 1, tzinfo=timezone.utc)
    hasta = datetime(2026, 1, 2, tzinfo=timezone.utc)

    resultado = use_case.execute(DISPOSITIVO_A, MEDIDOR_NAME, desde, hasta)

    assert "Carga 90kW" in resultado.protegidas
    assert len(resultado.actualizadas) == 0
    assert len(resultado.creadas) == 1

    # Verificar que la firma NO cambió
    carga_protegida = repo_vacio.obtener_por_id("c1")
    assert carga_protegida.firma.origen == OrigenFirma.CAMPANA


def test_sin_pareja_crea_carga_inactiva(repo_vacio):
    """Candidata sin emparejamiento → crea "Inferida ~50 kW" con activa=False."""
    # Descubridor con solo una candidata (sin competencia)
    descubridor = MockDescubridor(
        candidatas=[
            CargaCandidata(
                potencia_w=50000.0,
                dispersion_w=2000.0,
                encendidos=5,
                apagados=5,
                ciclos_por_dia=1.0,
                on_off=True,
            ),
        ]
    )

    use_case = ProponerFirmasInferidasUseCase(repo_vacio, descubridor)
    desde = datetime(2026, 1, 1, tzinfo=timezone.utc)
    hasta = datetime(2026, 1, 2, tzinfo=timezone.utc)

    resultado = use_case.execute(DISPOSITIVO_A, MEDIDOR_NAME, desde, hasta)

    assert len(resultado.creadas) == 1
    assert "Inferida ~50 kW" in resultado.creadas

    # Verificar que la carga fue creada inactiva
    carga_nueva = repo_vacio.obtener_por_nombre(DISPOSITIVO_A, "Inferida ~50 kW")
    assert carga_nueva is not None
    assert carga_nueva.activa is False
    assert carga_nueva.firma is not None
    assert carga_nueva.firma.origen == OrigenFirma.INFERIDA
    assert carga_nueva.firma.potencia_w == 50000.0


def test_idempotencia_segunda_corrida_no_crea_duplicados(repo_vacio):
    """Segunda corrida con igual candidata actualiza la "Inferida ~50 kW", no crea duplicado."""
    descubridor = MockDescubridor(
        candidatas=[
            CargaCandidata(
                potencia_w=50000.0,
                dispersion_w=2000.0,
                encendidos=5,
                apagados=5,
                ciclos_por_dia=1.0,
                on_off=True,
            ),
        ]
    )

    use_case = ProponerFirmasInferidasUseCase(repo_vacio, descubridor)
    desde = datetime(2026, 1, 1, tzinfo=timezone.utc)
    hasta = datetime(2026, 1, 2, tzinfo=timezone.utc)

    # Primera ejecución
    resultado1 = use_case.execute(DISPOSITIVO_A, MEDIDOR_NAME, desde, hasta)
    assert len(resultado1.creadas) == 1
    carga_id_1 = repo_vacio.obtener_por_nombre(DISPOSITIVO_A, "Inferida ~50 kW").id

    # Segunda ejecución (misma candidata)
    resultado2 = use_case.execute(DISPOSITIVO_A, MEDIDOR_NAME, desde, hasta)
    assert len(resultado2.creadas) == 0  # No crea nuevas
    assert len(resultado2.actualizadas) == 1  # Actualiza la existente

    # Verificar que sigue siendo la misma carga (idempotencia)
    carga_id_2 = repo_vacio.obtener_por_nombre(DISPOSITIVO_A, "Inferida ~50 kW").id
    assert carga_id_1 == carga_id_2


def test_candidata_on_off_false_es_descartada(repo_vacio, descubridor_con_candidatas):
    """Candidata con on_off=False → entra en descartadas, no se procesa."""
    use_case = ProponerFirmasInferidasUseCase(repo_vacio, descubridor_con_candidatas)
    desde = datetime(2026, 1, 1, tzinfo=timezone.utc)
    hasta = datetime(2026, 1, 2, tzinfo=timezone.utc)

    resultado = use_case.execute(DISPOSITIVO_A, MEDIDOR_NAME, desde, hasta)

    assert resultado.descartadas == 1  # La candidata on_off=False


def test_candidata_con_potencia_cero_es_descartada(repo_vacio):
    """Candidata con potencia <= 0 → descartada."""
    descubridor = MockDescubridor(
        candidatas=[
            CargaCandidata(
                potencia_w=0.0,
                dispersion_w=0.0,
                encendidos=0,
                apagados=0,
                ciclos_por_dia=None,
                on_off=True,
            ),
        ]
    )

    use_case = ProponerFirmasInferidasUseCase(repo_vacio, descubridor)
    desde = datetime(2026, 1, 1, tzinfo=timezone.utc)
    hasta = datetime(2026, 1, 2, tzinfo=timezone.utc)

    resultado = use_case.execute(DISPOSITIVO_A, MEDIDOR_NAME, desde, hasta)

    assert resultado.descartadas == 1
    assert len(resultado.creadas) == 0


def test_descubridor_no_disponible_propaga_excepcion(repo_vacio):
    """DescubridorNoDisponibleError se propaga hacia arriba."""
    descubridor_fallido = Mock(spec=DescubridorCargasPort)
    descubridor_fallido.descubrir.side_effect = DescubridorNoDisponibleError("energy-ml no responde")

    use_case = ProponerFirmasInferidasUseCase(repo_vacio, descubridor_fallido)
    desde = datetime(2026, 1, 1, tzinfo=timezone.utc)
    hasta = datetime(2026, 1, 2, tzinfo=timezone.utc)

    with pytest.raises(DescubridorNoDisponibleError):
        use_case.execute(DISPOSITIVO_A, MEDIDOR_NAME, desde, hasta)
