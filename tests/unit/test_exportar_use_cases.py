"""tests/unit/test_exportar_use_cases.py."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from src.application.use_cases.exportar_cargas import ExportarCargasUseCase
from src.application.use_cases.exportar_disponibilidad import (
    ExportarDisponibilidadUseCase,
)
from src.application.use_cases.exportar_telemetria import (
    ExportarTelemetriaUseCase,
)
from src.domain.maquinas.entities import Máquina, IntervaloActividadMáquina
from src.domain.maquinas.value_objects import CategoriaCarga
from src.domain.disponibilidad.entities import EventoDisponibilidad, Maquina
from src.domain.disponibilidad.exceptions import MaquinaNoEncontradaError
from src.domain.disponibilidad.value_objects import EstadoMaquina, TipoParada
from src.domain.telemetria.entities import LecturaInstantanea, MedicionFase
from src.domain.telemetria.value_objects import PotenciaActiva


def test_exportar_telemetria_use_case_ejecutar():
    repo_telemetria = MagicMock()
    lectura = LecturaInstantanea(
        id=1,
        dispositivo_id="dev-1",
        registrado_en=datetime(2026, 9, 7, 10, 0, 0, tzinfo=timezone.utc),
        fase_r=MedicionFase(potencia_activa=PotenciaActiva(vatios=100.0)),
        fase_s=MedicionFase(),
        fase_t=MedicionFase(),
    )
    repo_telemetria.iterar_instantaneas.return_value = iter([lectura])

    use_case = ExportarTelemetriaUseCase(repo_telemetria)
    stream = use_case.ejecutar(dispositivo_id="dev-1", limite=500)

    lineas = list(stream)
    assert len(lineas) == 3
    repo_telemetria.iterar_instantaneas.assert_called_once_with(
        dispositivo_id="dev-1",
        desde=None,
        hasta=None,
        limite=500,
    )


def test_exportar_disponibilidad_use_case_maquina_no_encontrada():
    repo_maquinas = MagicMock()
    repo_maquinas.obtener_por_id.return_value = None
    repo_eventos = MagicMock()

    use_case = ExportarDisponibilidadUseCase(repo_maquinas, repo_eventos)
    with pytest.raises(MaquinaNoEncontradaError):
        use_case.ejecutar("maq-inexistente")


def test_exportar_disponibilidad_use_case_ejecutar():
    repo_maquinas = MagicMock()
    repo_maquinas.obtener_por_id.return_value = Maquina(
        id="maq-1",
        dispositivo_id="dev-1",
        nombre="Torno CNC",
    )
    repo_eventos = MagicMock()
    evento = EventoDisponibilidad(
        id=1,
        maquina_id="maq-1",
        estado=EstadoMaquina.PARADA,
        tipo_parada=TipoParada.PROGRAMADA,
        inicio_at=datetime(2026, 9, 7, 8, 0, 0, tzinfo=timezone.utc),
        fin_at=datetime(2026, 9, 7, 8, 30, 0, tzinfo=timezone.utc),
        potencia_promedio_w=0.0,
    )
    repo_eventos.listar_por_rango.return_value = [evento]

    use_case = ExportarDisponibilidadUseCase(repo_maquinas, repo_eventos)
    stream = use_case.ejecutar("maq-1", dias=7)

    lineas = list(stream)
    assert len(lineas) >= 3
    assert any("Resumen OEE" in linea for linea in lineas)
    assert any("maq-1,PARADA,PROGRAMADA" in linea for linea in lineas)


def test_exportar_cargas_use_case_ejecutar():
    repo_cargas = MagicMock()
    repo_cargas.listar_por_dispositivo.return_value = [
        Máquina(id="c-1", dispositivo_id="dev-1", nombre="Bomba 1", categoria=CategoriaCarga.FUERZA_MOTRIZ)
    ]
    repo_intervalos = MagicMock()
    inter1 = IntervaloActividadMáquina(
        id=1,
        dispositivo_id="dev-1",
        inicio_at=datetime(2026, 9, 7, 8, 0, 0, tzinfo=timezone.utc),
        fin_at=datetime(2026, 9, 7, 8, 15, 0, tzinfo=timezone.utc),
        maquina_id="c-1",
        potencia_media_w=1500.0,
        energia_kwh=0.375,
    )
    inter2 = IntervaloActividadMáquina(
        id=2,
        dispositivo_id="dev-1",
        inicio_at=datetime(2026, 9, 7, 8, 15, 0, tzinfo=timezone.utc),
        fin_at=datetime(2026, 9, 7, 8, 30, 0, tzinfo=timezone.utc),
        maquina_id=None,
        potencia_media_w=500.0,
        energia_kwh=0.125,
    )
    repo_intervalos.listar_por_dispositivo.return_value = [inter1, inter2]

    use_case = ExportarCargasUseCase(repo_cargas, repo_intervalos)

    # Caso completo
    stream_todos = list(use_case.ejecutar("dev-1"))
    assert len(stream_todos) == 4  # BOM + Header + inter1 + inter2

    # Caso solo_no_atribuidos
    stream_no_atrib = list(use_case.ejecutar("dev-1", solo_no_atribuidos=True))
    assert len(stream_no_atrib) == 3  # BOM + Header + inter2
    assert "Bomba 1" not in "".join(stream_no_atrib)
    assert "NO_ATRIBUIDO" in stream_no_atrib[2]
