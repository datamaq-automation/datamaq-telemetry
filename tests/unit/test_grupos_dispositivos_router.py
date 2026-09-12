"""tests/unit/test_grupos_dispositivos_router.py — Tests unitarios para el router de grupos de dispositivos."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.application.dtos.grupo_dispositivos_dto import (
    GrupoDispositivosResponseDTO,
    PuntoPotenciaGrupoDTO,
    ResumenGrupoDispositivosDTO,
)
from src.domain.telemetria.exceptions import (
    DispositivoDePlantaDistintaError,
    GrupoDispositivosNoEncontradoError,
    LimiteGruposExcedidoError,
)
from src.infrastructure.fastapi.dependencies import (
    get_consultar_grupo_dispositivos_use_case,
    get_grupos_dispositivos_use_case,
    get_usuario_actual,
)
from src.infrastructure.fastapi.device_ownership import verificar_propiedad_grupo_dispositivos
from src.infrastructure.fastapi.server import create_app

AHORA = datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc)


def _grupo_dto(**kwargs) -> GrupoDispositivosResponseDTO:
    base = {
        "id": "grupo-1",
        "planta_id": "planta-1",
        "nombre": "Grupo Compresores",
        "dispositivos_ids": ["dev-1", "dev-2"],
        "creado_en": AHORA,
        "actualizado_en": AHORA,
    }
    base.update(kwargs)
    return GrupoDispositivosResponseDTO(**base)


def _cliente(rol: str = "admin") -> tuple[TestClient, dict[str, MagicMock]]:
    app = create_app()
    mocks = {
        "grupos": MagicMock(),
        "consultar": MagicMock(),
    }
    app.dependency_overrides[get_grupos_dispositivos_use_case] = lambda: mocks["grupos"]
    app.dependency_overrides[get_consultar_grupo_dispositivos_use_case] = lambda: mocks["consultar"]
    app.dependency_overrides[get_usuario_actual] = lambda: {
        "sub": "u1",
        "rol": rol,
        "org": "org-1",
    }
    app.dependency_overrides[verificar_propiedad_grupo_dispositivos] = lambda: None
    return TestClient(app), mocks


# --- CREAR GRUPO ---


def test_crear_grupo_exitoso():
    client, mocks = _cliente()
    mocks["grupos"].crear_grupo.return_value = _grupo_dto()

    payload = {
        "planta_id": "planta-1",
        "nombre": "Grupo Compresores",
        "dispositivos_ids": ["dev-1", "dev-2"],
    }
    response = client.post("/api/v1/grupos-dispositivos", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "grupo-1"
    assert data["nombre"] == "Grupo Compresores"
    assert data["dispositivos_ids"] == ["dev-1", "dev-2"]
    mocks["grupos"].crear_grupo.assert_called_once()
    dto_llamado = mocks["grupos"].crear_grupo.call_args[0][0]
    assert dto_llamado.planta_id == "planta-1"
    assert dto_llamado.nombre == "Grupo Compresores"


def test_crear_grupo_rol_invitado_rechazado_403():
    client, _ = _cliente(rol="invitado")

    payload = {
        "planta_id": "planta-1",
        "nombre": "Grupo Compresores",
        "dispositivos_ids": [],
    }
    response = client.post("/api/v1/grupos-dispositivos", json=payload)
    assert response.status_code == 403


def test_crear_grupo_limite_excedido_422():
    client, mocks = _cliente()
    mocks["grupos"].crear_grupo.side_effect = LimiteGruposExcedidoError("limite excedido")

    payload = {
        "planta_id": "planta-1",
        "nombre": "Grupo Nuevo",
        "dispositivos_ids": [],
    }
    response = client.post("/api/v1/grupos-dispositivos", json=payload)
    assert response.status_code == 422


def test_crear_grupo_dispositivo_planta_distinta_422():
    client, mocks = _cliente()
    mocks["grupos"].crear_grupo.side_effect = DispositivoDePlantaDistintaError("dispositivo de otra planta")

    payload = {
        "planta_id": "planta-1",
        "nombre": "Grupo Invalido",
        "dispositivos_ids": ["dev-99"],
    }
    response = client.post("/api/v1/grupos-dispositivos", json=payload)
    assert response.status_code == 422


def test_crear_grupo_error_inesperado_500():
    client, mocks = _cliente()
    mocks["grupos"].crear_grupo.side_effect = RuntimeError("db connection failed")

    payload = {
        "planta_id": "planta-1",
        "nombre": "Grupo Error",
        "dispositivos_ids": [],
    }
    response = client.post("/api/v1/grupos-dispositivos", json=payload)
    assert response.status_code == 500


# --- LISTAR GRUPOS ---


def test_listar_grupos_exitoso():
    client, mocks = _cliente()
    mocks["grupos"].listar_grupos.return_value = [_grupo_dto()]

    response = client.get("/api/v1/grupos-dispositivos?planta_id=planta-1")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == "grupo-1"
    assert data[0]["planta_id"] == "planta-1"
    mocks["grupos"].listar_grupos.assert_called_once_with("planta-1")


def test_listar_grupos_sin_planta_id_422():
    client, _ = _cliente()
    response = client.get("/api/v1/grupos-dispositivos")
    assert response.status_code == 422


# --- OBTENER GRUPO ---


def test_obtener_grupo_exitoso():
    client, mocks = _cliente()
    mocks["grupos"].obtener_grupo.return_value = _grupo_dto()

    response = client.get("/api/v1/grupos-dispositivos/grupo-1")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "grupo-1"
    mocks["grupos"].obtener_grupo.assert_called_once_with("grupo-1")


def test_obtener_grupo_no_encontrado_404():
    client, mocks = _cliente()
    mocks["grupos"].obtener_grupo.side_effect = GrupoDispositivosNoEncontradoError("grupo-404")

    response = client.get("/api/v1/grupos-dispositivos/grupo-404")
    assert response.status_code == 404


def test_obtener_grupo_error_inesperado_500():
    client, mocks = _cliente()
    mocks["grupos"].obtener_grupo.side_effect = Exception("error_inesperado")

    response = client.get("/api/v1/grupos-dispositivos/grupo-1")
    assert response.status_code == 500


# --- AGREGAR MIEMBRO ---


def test_agregar_miembro_exitoso():
    client, mocks = _cliente()
    mocks["grupos"].agregar_miembro.return_value = _grupo_dto(dispositivos_ids=["dev-1", "dev-2", "dev-3"])

    payload = {"dispositivo_id": "dev-3"}
    response = client.patch("/api/v1/grupos-dispositivos/grupo-1/miembros", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert "dev-3" in data["dispositivos_ids"]
    mocks["grupos"].agregar_miembro.assert_called_once_with("grupo-1", "dev-3")


def test_agregar_miembro_rol_invitado_rechazado_403():
    client, _ = _cliente(rol="invitado")

    payload = {"dispositivo_id": "dev-3"}
    response = client.patch("/api/v1/grupos-dispositivos/grupo-1/miembros", json=payload)
    assert response.status_code == 403


def test_agregar_miembro_grupo_no_encontrado_404():
    client, mocks = _cliente()
    mocks["grupos"].agregar_miembro.side_effect = GrupoDispositivosNoEncontradoError("grupo-99")

    payload = {"dispositivo_id": "dev-3"}
    response = client.patch("/api/v1/grupos-dispositivos/grupo-99/miembros", json=payload)
    assert response.status_code == 404


def test_agregar_miembro_dispositivo_planta_distinta_422():
    client, mocks = _cliente()
    mocks["grupos"].agregar_miembro.side_effect = DispositivoDePlantaDistintaError("dispositivo de otra planta")

    payload = {"dispositivo_id": "dev-99"}
    response = client.patch("/api/v1/grupos-dispositivos/grupo-1/miembros", json=payload)
    assert response.status_code == 422


def test_agregar_miembro_error_inesperado_500():
    client, mocks = _cliente()
    mocks["grupos"].agregar_miembro.side_effect = Exception("error_inesperado")

    payload = {"dispositivo_id": "dev-3"}
    response = client.patch("/api/v1/grupos-dispositivos/grupo-1/miembros", json=payload)
    assert response.status_code == 500


# --- QUITAR MIEMBRO ---


def test_quitar_miembro_exitoso():
    client, mocks = _cliente()
    mocks["grupos"].quitar_miembro.return_value = _grupo_dto(dispositivos_ids=["dev-1"])

    response = client.delete("/api/v1/grupos-dispositivos/grupo-1/miembros/dev-2")
    assert response.status_code == 200
    data = response.json()
    assert data["dispositivos_ids"] == ["dev-1"]
    mocks["grupos"].quitar_miembro.assert_called_once_with("grupo-1", "dev-2")


def test_quitar_miembro_rol_invitado_rechazado_403():
    client, _ = _cliente(rol="invitado")

    response = client.delete("/api/v1/grupos-dispositivos/grupo-1/miembros/dev-2")
    assert response.status_code == 403


def test_quitar_miembro_grupo_no_encontrado_404():
    client, mocks = _cliente()
    mocks["grupos"].quitar_miembro.side_effect = GrupoDispositivosNoEncontradoError("grupo-99")

    response = client.delete("/api/v1/grupos-dispositivos/grupo-99/miembros/dev-2")
    assert response.status_code == 404


def test_quitar_miembro_error_inesperado_500():
    client, mocks = _cliente()
    mocks["grupos"].quitar_miembro.side_effect = Exception("error_inesperado")

    response = client.delete("/api/v1/grupos-dispositivos/grupo-1/miembros/dev-2")
    assert response.status_code == 500


# --- ELIMINAR GRUPO ---


def test_eliminar_grupo_exitoso():
    client, mocks = _cliente()
    mocks["grupos"].eliminar_grupo.return_value = None

    response = client.delete("/api/v1/grupos-dispositivos/grupo-1")
    assert response.status_code == 200
    assert response.json() == {"detail": "grupo_eliminado"}
    mocks["grupos"].eliminar_grupo.assert_called_once_with("grupo-1")


def test_eliminar_grupo_rol_invitado_rechazado_403():
    client, _ = _cliente(rol="invitado")

    response = client.delete("/api/v1/grupos-dispositivos/grupo-1")
    assert response.status_code == 403


def test_eliminar_grupo_no_encontrado_404():
    client, mocks = _cliente()
    mocks["grupos"].eliminar_grupo.side_effect = GrupoDispositivosNoEncontradoError("grupo-99")

    response = client.delete("/api/v1/grupos-dispositivos/grupo-99")
    assert response.status_code == 404


def test_eliminar_grupo_error_inesperado_500():
    client, mocks = _cliente()
    mocks["grupos"].eliminar_grupo.side_effect = Exception("error_inesperado")

    response = client.delete("/api/v1/grupos-dispositivos/grupo-1")
    assert response.status_code == 500


# --- RESUMEN GRUPO ---


def test_resumen_grupo_exitoso():
    client, mocks = _cliente()
    mocks["consultar"].resumen.return_value = ResumenGrupoDispositivosDTO(
        grupo_id="grupo-1",
        potencia_activa_total_w=1200.5,
        dispositivos_sin_dato=[],
        energia_agregada=[],
    )

    response = client.get(
        "/api/v1/grupos-dispositivos/grupo-1/resumen?granularity=day&timezone=America/Argentina/Buenos_Aires&dias=7"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["grupo_id"] == "grupo-1"
    assert data["potencia_activa_total_w"] == 1200.5
    mocks["consultar"].resumen.assert_called_once_with("grupo-1", "day", "America/Argentina/Buenos_Aires", 7)


def test_resumen_grupo_no_encontrado_404():
    client, mocks = _cliente()
    mocks["consultar"].resumen.side_effect = GrupoDispositivosNoEncontradoError("grupo-404")

    response = client.get("/api/v1/grupos-dispositivos/grupo-404/resumen")
    assert response.status_code == 404


def test_resumen_grupo_error_inesperado_500():
    client, mocks = _cliente()
    mocks["consultar"].resumen.side_effect = Exception("error_inesperado")

    response = client.get("/api/v1/grupos-dispositivos/grupo-1/resumen")
    assert response.status_code == 500


# --- HISTORICO GRUPO ---


def test_historico_grupo_exitoso():
    client, mocks = _cliente()
    mocks["consultar"].historico.return_value = [
        PuntoPotenciaGrupoDTO(
            momento=AHORA,
            potencia_activa_total_w=3400.0,
            dispositivos_sin_dato=[],
        )
    ]

    response = client.get("/api/v1/grupos-dispositivos/grupo-1/resumen/historico?hours=12&granularity=15m")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["potencia_activa_total_w"] == 3400.0
    mocks["consultar"].historico.assert_called_once_with("grupo-1", "15m", 12)


def test_historico_grupo_no_encontrado_404():
    client, mocks = _cliente()
    mocks["consultar"].historico.side_effect = GrupoDispositivosNoEncontradoError("grupo-404")

    response = client.get("/api/v1/grupos-dispositivos/grupo-404/resumen/historico")
    assert response.status_code == 404


def test_historico_grupo_error_inesperado_500():
    client, mocks = _cliente()
    mocks["consultar"].historico.side_effect = Exception("error_inesperado")

    response = client.get("/api/v1/grupos-dispositivos/grupo-1/resumen/historico")
    assert response.status_code == 500
