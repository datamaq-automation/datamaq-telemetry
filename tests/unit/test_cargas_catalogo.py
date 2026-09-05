"""Catálogo de cargas: alta, edición, unicidad por medidor y firma manual."""

import pytest

from src.application.dtos.carga_dto import (
    CargaCreateDTO,
    CargaUpdateDTO,
    FirmaManualRequestDTO,
)
from src.application.use_cases.gestionar_cargas import GestionarCargasUseCase
from src.domain.cargas.entities import Carga
from src.domain.cargas.exceptions import (
    CargaDuplicadaError,
    CargaNoEncontradaError,
    FirmaCargaInvalidaError,
)
from src.domain.cargas.ports import RepositorioCargasPort
from src.domain.cargas.value_objects import (
    CategoriaCarga,
    FirmaCarga,
    NaturalezaElectrica,
    OrigenFirma,
    PatronOperacion,
)

MEDIDOR_CASA = "d48c49f0-3564-4000-8000-000000000001"
OTRO_MEDIDOR = "d48c49f0-3564-4000-8000-000000000002"


class MockCargasRepo(RepositorioCargasPort):
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


@pytest.fixture
def use_case() -> GestionarCargasUseCase:
    return GestionarCargasUseCase(MockCargasRepo())


def _crear(use_case: GestionarCargasUseCase, nombre: str, **kwargs):
    return use_case.registrar_carga(
        CargaCreateDTO(nombre=nombre, dispositivo_id=kwargs.pop("dispositivo_id", MEDIDOR_CASA), **kwargs)
    )


def test_registrar_carga_arranca_sin_firma_pero_con_potencia_esperada_de_chapa(use_case):
    """La chapa sirve de prior aunque todavía no haya firma medida."""
    dto = _crear(
        use_case,
        "Pava eléctrica",
        categoria=CategoriaCarga.COCCION,
        naturaleza_electrica=NaturalezaElectrica.RESISTIVA,
        potencia_nominal_w=2000.0,
    )

    assert dto.esta_caracterizada is False
    assert dto.firma is None
    assert dto.potencia_esperada_w == 2000.0
    assert dto.patron_operacion == PatronOperacion.INDETERMINADO
    assert dto.activa is True


def test_un_medidor_agregado_admite_muchas_cargas(use_case):
    """A diferencia de `Maquina` (1:1 con el dispositivo), la relación acá es N:1."""
    for nombre in ("Heladera", "Freezer", "Termotanque", "Lavarropas"):
        _crear(use_case, nombre)

    assert len(use_case.listar_cargas(dispositivo_id=MEDIDOR_CASA)) == 4


def test_no_se_admiten_dos_cargas_con_el_mismo_nombre_en_el_mismo_medidor(use_case):
    _crear(use_case, "Heladera")

    with pytest.raises(CargaDuplicadaError):
        _crear(use_case, "Heladera")


def test_el_mismo_nombre_en_otro_medidor_es_valido(use_case):
    """La unicidad es por medidor: dos domicilios pueden tener cada uno su heladera."""
    _crear(use_case, "Heladera")
    otra = _crear(use_case, "Heladera", dispositivo_id=OTRO_MEDIDOR)

    assert otra.dispositivo_id == OTRO_MEDIDOR


def test_renombrar_hacia_un_nombre_ya_usado_en_el_medidor_falla(use_case):
    _crear(use_case, "Heladera")
    freezer = _crear(use_case, "Freezer")

    with pytest.raises(CargaDuplicadaError):
        use_case.actualizar_carga(freezer.id, CargaUpdateDTO(nombre="Heladera"))


def test_renombrar_una_carga_a_su_propio_nombre_no_es_colision(use_case):
    heladera = _crear(use_case, "Heladera")

    actualizada = use_case.actualizar_carga(heladera.id, CargaUpdateDTO(nombre="Heladera"))

    assert actualizada.nombre == "Heladera"


def test_actualizar_carga_inexistente_falla(use_case):
    with pytest.raises(CargaNoEncontradaError):
        use_case.actualizar_carga("no-existe", CargaUpdateDTO(nombre="X"))


def test_listar_solo_activas_excluye_las_dadas_de_baja(use_case):
    _crear(use_case, "Heladera")
    anafe = _crear(use_case, "Anafe eléctrico")
    use_case.actualizar_carga(anafe.id, CargaUpdateDTO(activa=False))

    activas = use_case.listar_cargas(dispositivo_id=MEDIDOR_CASA, solo_activas=True)

    assert [c.nombre for c in activas] == ["Heladera"]


def test_listar_sin_dispositivo_devuelve_todas_las_cargas(use_case):
    _crear(use_case, "Heladera")
    _crear(use_case, "Horno", dispositivo_id=OTRO_MEDIDOR)

    assert len(use_case.listar_cargas()) == 2


def test_fijar_firma_manual_queda_marcada_como_chapa(use_case):
    """Una firma declarada a mano no fue medida: debe confesar su origen."""
    pava = _crear(use_case, "Pava eléctrica")

    actualizada = use_case.fijar_firma_manual(
        pava.id,
        FirmaManualRequestDTO(potencia_w=1850.0, dispersion_w=90.0, factor_potencia=0.99, duracion_encendido_s=180.0),
    )

    assert actualizada.esta_caracterizada is True
    assert actualizada.firma is not None
    assert actualizada.firma.origen == OrigenFirma.CHAPA
    assert actualizada.firma.muestras == 0
    assert actualizada.firma.es_resistiva is True
    assert actualizada.firma.esta_completa is True
    assert actualizada.potencia_esperada_w == 1850.0


def test_la_firma_medida_le_gana_a_la_potencia_de_chapa(use_case):
    pava = _crear(use_case, "Pava eléctrica", potencia_nominal_w=2000.0)

    actualizada = use_case.fijar_firma_manual(pava.id, FirmaManualRequestDTO(potencia_w=1850.0))

    assert actualizada.potencia_nominal_w == 2000.0
    assert actualizada.potencia_esperada_w == 1850.0


def test_una_firma_con_dispersion_mayor_que_la_potencia_es_rechazada(use_case):
    """Describiría una carga que se apaga y prende sola: no es una carga física."""
    pava = _crear(use_case, "Pava eléctrica")

    with pytest.raises(FirmaCargaInvalidaError):
        use_case.fijar_firma_manual(pava.id, FirmaManualRequestDTO(potencia_w=1800.0, dispersion_w=2000.0))


def test_firma_sin_duracion_no_esta_completa():
    """Sin duración no se puede separar una pava de un termotanque: la firma queda a medias."""
    firma = FirmaCarga(potencia_w=1800.0, dispersion_w=50.0, factor_potencia=0.99)

    assert firma.es_resistiva is True
    assert firma.esta_completa is False


def test_firma_sin_factor_de_potencia_no_se_declara_resistiva():
    """Sin FP medido no se afirma la naturaleza eléctrica."""
    firma = FirmaCarga(potencia_w=1800.0, dispersion_w=50.0, duracion_encendido_s=180.0)

    assert firma.es_resistiva is False
