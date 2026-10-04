"""tests/unit/test_cargas_campanas.py — Campañas de caracterización: apertura, captura, cierre y calibración."""

from datetime import datetime, timedelta, timezone

import pytest

from src.application.dtos.maquina_dto import CampanaCreateDTO
from src.application.use_cases.caracterizar_carga import CaracterizarCargaUseCase
from src.application.use_cases.ingesta.registro_campanas import RegistroCampanasActivas
from src.domain.maquinas.entities import EnsayoCaracterizacion, Máquina
from src.domain.maquinas.exceptions import (
    EnsayoEnCursoError,
    EnsayoNoEncontradoError,
    EnsayoYaCerradoError,
    MáquinaNoEncontradaError,
)
from src.domain.maquinas.ports import ComandoRafagaPort, RepositorioEnsayosPort
from src.domain.maquinas.value_objects import (
    EstadoCampana,
    MotivoDescarte,
    MuestraCampana,
    OrigenFirma,
    TipoCampana,
)
from src.domain.telemetria.entities import Dispositivo
from src.domain.telemetria.exceptions import DispositivoNoEncontradoError
from src.domain.telemetria.ports import RepositorioDispositivosPort
from src.domain.telemetria.value_objects import MacAddress
from tests.unit.test_cargas_catalogo import MEDIDOR_CASA, MockCargasRepo

UID = "D48C49F03564"
AHORA = datetime(2026, 9, 4, 15, 0, tzinfo=timezone.utc)


class MockCampanasRepo(RepositorioEnsayosPort):
    def __init__(self):
        self.campanas: dict[str, EnsayoCaracterizacion] = {}
        self.muestras: dict[str, list[MuestraCampana]] = {}

    def obtener_por_id(self, campana_id):
        return self.campanas.get(campana_id)

    def obtener_en_curso_por_dispositivo(self, dispositivo_id):
        return next(
            (
                c
                for c in self.campanas.values()
                if c.dispositivo_id == dispositivo_id and c.estado == EstadoCampana.EN_CURSO
            ),
            None,
        )

    def listar_en_curso(self):
        return [c for c in self.campanas.values() if c.estado == EstadoCampana.EN_CURSO]

    def listar_por_carga(self, carga_id):
        return [c for c in self.campanas.values() if c.carga_id == carga_id]

    def guardar(self, campana):
        self.campanas[campana.id] = campana
        return campana

    def agregar_muestra(self, campana_id, muestra):
        existentes = self.muestras.setdefault(campana_id, [])
        if any(m.momento == muestra.momento for m in existentes):
            return False
        existentes.append(muestra)
        return True

    def listar_muestras(self, campana_id):
        return sorted(self.muestras.get(campana_id, []), key=lambda m: m.momento)


class MockDispositivosRepo(RepositorioDispositivosPort):
    def __init__(self, con_dispositivo: bool = True):
        self.dispositivos = (
            {MEDIDOR_CASA: Dispositivo(id=MEDIDOR_CASA, device_uid=MacAddress(UID), nombre="Casa")}
            if con_dispositivo
            else {}
        )

    def obtener_por_id(self, dispositivo_id):
        return self.dispositivos.get(dispositivo_id)

    def obtener_por_uid(self, uid):
        return next((d for d in self.dispositivos.values() if d.device_uid.valor == uid.valor), None)

    def listar(self, planta_id=None):
        return list(self.dispositivos.values())

    def contar_por_organizacion(self, organizacion_id):
        return len(self.dispositivos)

    def guardar(self, dispositivo):
        self.dispositivos[dispositivo.id] = dispositivo
        return dispositivo

    def actualizar_heartbeat(
        self, dispositivo_id, estado, visto_por_ultima_vez, numero_serie=None, version_fw=None, version_hw=None
    ) -> None:
        d = self.dispositivos.get(dispositivo_id)
        if d:
            d.estado = estado
            d.visto_por_ultima_vez = visto_por_ultima_vez
            if numero_serie:
                d.numero_serie = numero_serie
            if version_fw:
                d.version_fw = version_fw
            if version_hw:
                d.version_hw = version_hw


class MockRafaga(ComandoRafagaPort):
    def __init__(self, ok: bool = True):
        self.ok = ok
        self.llamadas: list[tuple[str, int]] = []

    def activar_rafaga(self, device_uid: str, segundos: int) -> bool:
        self.llamadas.append((device_uid, segundos))
        return self.ok


@pytest.fixture
def contexto():
    campanas, maquinas = MockCampanasRepo(), MockCargasRepo()
    maquinas.guardar(Máquina(id="maquina-pava", dispositivo_id=MEDIDOR_CASA, nombre="Pava eléctrica"))
    registro, rafaga = RegistroCampanasActivas(), MockRafaga()
    use_case = CaracterizarCargaUseCase(campanas, maquinas, MockDispositivosRepo(), registro, rafaga)
    return use_case, campanas, maquinas, registro, rafaga


def _dto(duracion: int = 300, carga_id: str | None = "maquina-pava") -> CampanaCreateDTO:
    return CampanaCreateDTO(dispositivo_id=MEDIDOR_CASA, duracion_segundos=duracion, carga_id=carga_id)


def test_iniciar_una_campana_pide_la_rafaga_al_medidor(contexto):
    use_case, _, _, _, rafaga = contexto

    dto = use_case.iniciar_activa(_dto())

    assert dto.estado == EstadoCampana.EN_CURSO
    assert dto.tipo == TipoCampana.ACTIVA
    assert dto.rafaga_solicitada is True
    assert rafaga.llamadas == [(UID, CaracterizarCargaUseCase.SEGUNDOS_RAFAGA)]


def test_la_campana_queda_registrada_para_que_la_ingesta_capture(contexto):
    use_case, _, _, registro, _ = contexto

    dto = use_case.iniciar_activa(_dto())

    assert registro.campana_de(MEDIDOR_CASA) == dto.id


def test_no_se_pueden_abrir_dos_campanas_sobre_el_mismo_medidor(contexto):
    """Medirían la misma señal agregada y ninguna podría atribuirse su parte."""
    use_case, _, _, _, _ = contexto
    use_case.iniciar_activa(_dto())

    with pytest.raises(EnsayoEnCursoError):
        use_case.iniciar_activa(_dto())


def test_una_campana_sobre_una_carga_inexistente_falla(contexto):
    use_case, _, _, _, _ = contexto

    with pytest.raises(MáquinaNoEncontradaError):
        use_case.iniciar_activa(_dto(carga_id="no-existe"))


def test_una_campana_sobre_un_dispositivo_inexistente_falla(contexto):
    _, campanas, maquinas, registro, rafaga = contexto
    use_case = CaracterizarCargaUseCase(campanas, maquinas, MockDispositivosRepo(con_dispositivo=False), registro, rafaga)

    with pytest.raises(DispositivoNoEncontradoError):
        use_case.iniciar_activa(_dto())


def test_la_campana_se_abre_igual_si_el_broker_no_responde(contexto):
    """Con un cliente WebSocket conectado el medidor ya está en ráfaga por otro camino."""
    _, campanas, maquinas, registro, _ = contexto
    use_case = CaracterizarCargaUseCase(campanas, maquinas, MockDispositivosRepo(), registro, MockRafaga(ok=False))

    dto = use_case.iniciar_activa(_dto())

    assert dto.estado == EstadoCampana.EN_CURSO
    assert dto.rafaga_solicitada is False


def _cargar_muestras(campanas: MockCampanasRepo, campana_id: str, potencias: list[float]) -> None:
    campanas.muestras[campana_id] = [
        MuestraCampana(momento=AHORA + timedelta(seconds=i), potencia_w=p, potencia_reactiva_var=5.0)
        for i, p in enumerate(potencias)
    ]


def test_finalizar_una_campana_limpia_fija_la_firma_en_la_carga(contexto):
    use_case, campanas, maquinas, registro, _ = contexto
    campana = use_case.iniciar_activa(_dto())
    _cargar_muestras(campanas, campana.id, [140.0] * 70 + [1990.0] * 180)

    resultado = use_case.finalizar(campana.id)

    assert resultado.estado == EstadoCampana.COMPLETADA
    assert resultado.resultado is not None
    assert resultado.resultado.firma is not None
    firma = maquinas.obtener_por_id("maquina-pava").firma
    assert firma is not None
    assert firma.potencia_w == 1850.0
    assert firma.origen == OrigenFirma.CAMPANA
    assert registro.campana_de(MEDIDOR_CASA) is None


def test_una_campana_contaminada_no_fija_ninguna_firma(contexto):
    """La firma se usaría a ciegas durante meses; repetir la campaña cuesta diez minutos."""
    use_case, campanas, maquinas, _, _ = contexto
    campana = use_case.iniciar_activa(_dto())
    _cargar_muestras(campanas, campana.id, [140.0] * 70 + [1990.0] * 90 + [3990.0] * 90)

    resultado = use_case.finalizar(campana.id)

    assert resultado.estado == EstadoCampana.CONTAMINADA
    assert resultado.motivo_descarte is not None
    assert maquinas.obtener_por_id("maquina-pava").firma is None


def test_una_campana_sin_muestras_avisa_que_no_hubo_rafaga(contexto):
    use_case, _, _, _, _ = contexto
    campana = use_case.iniciar_activa(_dto())

    resultado = use_case.finalizar(campana.id)

    assert resultado.motivo_descarte == MotivoDescarte.SIN_MUESTRAS
    assert resultado.notas is not None
    assert "modo ráfaga" in resultado.notas


def test_no_se_puede_finalizar_dos_veces(contexto):
    use_case, _, _, _, _ = contexto
    campana = use_case.iniciar_activa(_dto())
    use_case.finalizar(campana.id)

    with pytest.raises(EnsayoYaCerradoError):
        use_case.finalizar(campana.id)


def test_descartar_libera_el_medidor_sin_calibrar_nada(contexto):
    use_case, _, maquinas, registro, _ = contexto
    campana = use_case.iniciar_activa(_dto())

    resultado = use_case.descartar(campana.id, motivo="me equivoqué de aparato")

    assert resultado.estado == EstadoCampana.DESCARTADA
    assert resultado.notas == "me equivoqué de aparato"
    assert registro.campana_de(MEDIDOR_CASA) is None
    assert maquinas.obtener_por_id("maquina-pava").firma is None


def test_campana_inexistente_falla(contexto):
    use_case, _, _, _, _ = contexto

    with pytest.raises(EnsayoNoEncontradoError):
        use_case.obtener("no-existe")


def test_sostener_renueva_la_rafaga_de_las_campanas_vivas(contexto):
    """La ráfaga del firmware es una duración: sin renovación el medidor vuelve a 5 min."""
    use_case, _, _, _, rafaga = contexto
    use_case.iniciar_activa(_dto(duracion=3600))
    rafaga.llamadas.clear()

    renovadas, cerradas = use_case.sostener_campanas_activas()

    assert (renovadas, cerradas) == (1, 0)
    assert rafaga.llamadas == [(UID, CaracterizarCargaUseCase.SEGUNDOS_RAFAGA)]


def test_sostener_cierra_las_campanas_vencidas(contexto):
    """Una campaña olvidada dejaría al medidor en ráfaga y escribiendo indefinidamente."""
    use_case, campanas, _, registro, _ = contexto
    campana = use_case.iniciar_activa(_dto(duracion=60))
    campanas.campanas[campana.id].fin_planificado_at = AHORA - timedelta(hours=1)

    renovadas, cerradas = use_case.sostener_campanas_activas()

    assert (renovadas, cerradas) == (0, 1)
    assert campanas.campanas[campana.id].estado != EstadoCampana.EN_CURSO
    assert registro.campana_de(MEDIDOR_CASA) is None


def test_sostener_rehidrata_el_registro_tras_un_reinicio(contexto):
    """La fuente de verdad es la tabla; el registro en memoria arranca vacío."""
    use_case, _, _, registro, _ = contexto
    use_case.iniciar_activa(_dto(duracion=3600))
    registro.limpiar()

    use_case.sostener_campanas_activas()

    assert registro.campana_de(MEDIDOR_CASA) is not None
