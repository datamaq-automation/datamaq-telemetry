"""tests/unit/test_pro15_identidad.py — identidad (MAC, medidor_id) del Pro15.

Escritos según specs/ingesta-pro15-multimedidor.md (sección 4).
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

from src.application.use_cases.ingesta.resolvedor_dispositivo import ResolvedorDispositivoIngesta
from src.application.use_cases.ingestar_telemetria import IngestarTelemetriaUseCase
from src.domain.telemetria.value_objects import MacAddress

MAC = "8C8C291C3FB4"
AHORA = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)


def _repo_vacio() -> MagicMock:
    repo = MagicMock()
    repo.obtener_por_uid.return_value = None
    repo.guardar.side_effect = lambda disp: disp
    return repo


def test_regresion_topic_pro15_nunca_registra_inst_ni_v1():
    # La trampa: partes[2] del topic pro15 es el subtópico ("inst"). El caso de uso genérico no debe
    # resolver ni registrar ningún dispositivo a partir de él.
    repo = _repo_vacio()
    caso = IngestarTelemetriaUseCase(repo_dispositivos=repo, repo_telemetria=MagicMock())

    for topico in (f"pro15/{MAC}/inst/v1", f"pro15/{MAC}/acc/v1", f"pro15/{MAC}/thd/v1"):
        caso.ejecutar(topico, {"device_info": {"model": "Smart Pro15"}, "f": []})

    repo.obtener_por_uid.assert_not_called()
    repo.guardar.assert_not_called()


def test_dos_medidores_de_la_misma_mac_son_dispositivos_distintos():
    ResolvedorDispositivoIngesta.limpiar_cache()
    repo = _repo_vacio()
    uid = MacAddress(MAC)

    medidor0 = ResolvedorDispositivoIngesta.obtener_o_crear_dispositivo(MAC, None, AHORA, repo, medidor_id=0)
    medidor1 = ResolvedorDispositivoIngesta.obtener_o_crear_dispositivo(MAC, None, AHORA, repo, medidor_id=1)

    assert medidor0 is not None and medidor1 is not None
    assert medidor0.id != medidor1.id
    assert (medidor0.medidor_id, medidor1.medidor_id) == (0, 1)
    assert medidor0.device_uid == medidor1.device_uid == uid


def test_cache_no_mezcla_medidores_de_la_misma_mac():
    ResolvedorDispositivoIngesta.limpiar_cache()
    repo = _repo_vacio()

    medidor0 = ResolvedorDispositivoIngesta.obtener_o_crear_dispositivo(MAC, None, AHORA, repo, medidor_id=0)
    medidor1 = ResolvedorDispositivoIngesta.obtener_o_crear_dispositivo(MAC, None, AHORA, repo, medidor_id=1)

    # Segunda llamada dentro del mismo minuto: sale de la caché y debe devolver su propio medidor.
    assert ResolvedorDispositivoIngesta.obtener_o_crear_dispositivo(MAC, None, AHORA, repo, medidor_id=1) is medidor1
    assert ResolvedorDispositivoIngesta.obtener_o_crear_dispositivo(MAC, None, AHORA, repo, medidor_id=0) is medidor0


def test_lookup_sin_medidor_resuelve_el_medidor_0_explicito():
    ResolvedorDispositivoIngesta.limpiar_cache()
    repo = _repo_vacio()
    ResolvedorDispositivoIngesta.obtener_o_crear_dispositivo(MAC, None, AHORA, repo, medidor_id=1)

    # Solo se cargó el medidor 1. La resolución por MAC (medidor 0) no debe tomar la fila del medidor 1.
    assert ResolvedorDispositivoIngesta.resolver_organizacion_id(MAC, MagicMock()) is None


def test_repositorio_obtener_por_uid_filtra_por_medidor():
    from src.infrastructure.sqlalchemy.repositories.dispositivos_repository import MySQLDispositivosRepository

    db = MagicMock()
    query = db.query.return_value
    query.filter.return_value.one_or_none.return_value = None

    MySQLDispositivosRepository(db).obtener_por_uid(MacAddress(MAC), 1)

    filtro = query.filter.call_args
    assert filtro is not None
    # El filtro incluye la columna de medidor; no se usa .first() sobre solo la MAC.
    query.filter.return_value.one_or_none.assert_called_once()
