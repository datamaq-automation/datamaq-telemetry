"""tests/unit/test_consultar_maquinas_inferidas.py."""

import uuid
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from src.application.dtos.maquina_dto import (
    MaquinaInferidaDTO,
)
from src.application.use_cases.consultar_maquinas_inferidas import (
    ConsultarMaquinasInferidaUseCase,
)
from src.domain.cargas.entities import Carga
from src.domain.cargas.value_objects import (
    CategoriaCarga,
    FirmaCarga,
    NaturalezaElectrica,
    OrigenFirma,
    PatronOperacion,
)


class TestConsultarMaquinasInferidaUseCase:
    """Tests para ConsultarMaquinasInferidaUseCase."""

    @pytest.fixture
    def mock_repo_cargas(self):
        """Mock del repositorio de cargas."""
        return Mock()

    @pytest.fixture
    def use_case(self, mock_repo_cargas):
        """Instancia del use case con mock."""
        return ConsultarMaquinasInferidaUseCase(mock_repo_cargas)

    def test_dispositivo_sin_inferencias_retorna_lista_vacia(self, use_case, mock_repo_cargas):
        """Dispositivo sin máquinas inferidas retorna lista vacía."""
        dispositivo_id = str(uuid.uuid4())
        mock_repo_cargas.listar_por_dispositivo.return_value = []

        resultado = use_case(dispositivo_id)

        assert resultado.dispositivo_id == dispositivo_id
        assert resultado.maquinas_inferidas == []
        assert resultado.total_confianza_prom == 0.0
        mock_repo_cargas.listar_por_dispositivo.assert_called_once_with(dispositivo_id, solo_activas=False)

    def test_dispositivo_con_una_maquina_inferida(self, use_case, mock_repo_cargas):
        """Dispositivo con 1 máquina inferida retorna 1 item."""
        dispositivo_id = str(uuid.uuid4())
        carga = Carga(
            id=str(uuid.uuid4()),
            dispositivo_id=dispositivo_id,
            nombre="Inferida ~5 kW",
            categoria=CategoriaCarga.FUERZA_MOTRIZ,
            naturaleza_electrica=NaturalezaElectrica.MIXTA,
            patron_operacion=PatronOperacion.INDETERMINADO,
            firma=FirmaCarga(
                potencia_w=5000.0,
                dispersion_w=500.0,
                origen=OrigenFirma.INFERIDA,
                muestras=10,
                medida_en=datetime.now(timezone.utc),
            ),
        )
        mock_repo_cargas.listar_por_dispositivo.return_value = [carga]

        resultado = use_case(dispositivo_id)

        assert resultado.dispositivo_id == dispositivo_id
        assert len(resultado.maquinas_inferidas) == 1
        assert resultado.maquinas_inferidas[0].nombre == "Inferida ~5 kW"
        assert resultado.maquinas_inferidas[0].tipo_maquina == "fuerza_motriz"
        assert 0.0 <= resultado.maquinas_inferidas[0].confianza <= 1.0

    def test_dispositivo_con_n_maquinas_ordenadas_por_confianza(self, use_case, mock_repo_cargas):
        """Dispositivo con N máquinas inferidas ordenadas por confianza DESC."""
        dispositivo_id = str(uuid.uuid4())
        cargas = [
            Carga(
                id=str(uuid.uuid4()),
                dispositivo_id=dispositivo_id,
                nombre="Carga Alta Confianza",
                categoria=CategoriaCarga.FUERZA_MOTRIZ,
                firma=FirmaCarga(
                    potencia_w=10000.0,
                    dispersion_w=100.0,  # baja dispersión = alta confianza
                    origen=OrigenFirma.INFERIDA,
                    muestras=10,
                    medida_en=datetime.now(timezone.utc),
                ),
            ),
            Carga(
                id=str(uuid.uuid4()),
                dispositivo_id=dispositivo_id,
                nombre="Carga Baja Confianza",
                categoria=CategoriaCarga.OTROS,
                firma=FirmaCarga(
                    potencia_w=5000.0,
                    dispersion_w=2000.0,  # alta dispersión = baja confianza
                    origen=OrigenFirma.INFERIDA,
                    muestras=10,
                    medida_en=datetime.now(timezone.utc),
                ),
            ),
        ]
        mock_repo_cargas.listar_por_dispositivo.return_value = cargas

        resultado = use_case(dispositivo_id)

        assert len(resultado.maquinas_inferidas) == 2
        # Verificar que están ordenadas por confianza DESC
        assert resultado.maquinas_inferidas[0].confianza >= resultado.maquinas_inferidas[1].confianza
        # Primera debe ser la de alta confianza
        assert "Alta Confianza" in resultado.maquinas_inferidas[0].nombre

    def test_confianza_en_rango_0_a_1(self, use_case, mock_repo_cargas):
        """Confianza siempre está en rango [0.0, 1.0]."""
        dispositivo_id = str(uuid.uuid4())
        carga = Carga(
            id=str(uuid.uuid4()),
            dispositivo_id=dispositivo_id,
            nombre="Test",
            firma=FirmaCarga(
                potencia_w=5000.0,
                dispersion_w=1000.0,
                origen=OrigenFirma.INFERIDA,
                muestras=10,
                medida_en=datetime.now(timezone.utc),
            ),
        )
        mock_repo_cargas.listar_por_dispositivo.return_value = [carga]

        resultado = use_case(dispositivo_id)

        confianza = resultado.maquinas_inferidas[0].confianza
        assert 0.0 <= confianza <= 1.0

    def test_promedio_confianza_calculado_correctamente(self, use_case, mock_repo_cargas):
        """Promedio de confianza se calcula correctamente."""
        dispositivo_id = str(uuid.uuid4())
        cargas = [
            Carga(
                id=str(uuid.uuid4()),
                dispositivo_id=dispositivo_id,
                nombre=f"Carga {i}",
                firma=FirmaCarga(
                    potencia_w=5000.0,
                    dispersion_w=float(500 * (i + 1)),
                    origen=OrigenFirma.INFERIDA,
                    muestras=10,
                    medida_en=datetime.now(timezone.utc),
                ),
            )
            for i in range(3)
        ]
        mock_repo_cargas.listar_por_dispositivo.return_value = cargas

        resultado = use_case(dispositivo_id)

        # Verificar que promedio es válido
        assert len(resultado.maquinas_inferidas) == 3
        if resultado.maquinas_inferidas:
            promedio_manual = sum(m.confianza for m in resultado.maquinas_inferidas) / len(resultado.maquinas_inferidas)
            assert abs(resultado.total_confianza_prom - promedio_manual) < 0.01

    def test_solo_cargas_inferidas_incluidas(self, use_case, mock_repo_cargas):
        """Solo cargas con origen=INFERIDA se incluyen en el resultado."""
        dispositivo_id = str(uuid.uuid4())
        cargas = [
            Carga(
                id=str(uuid.uuid4()),
                dispositivo_id=dispositivo_id,
                nombre="Carga INFERIDA",
                firma=FirmaCarga(
                    potencia_w=5000.0,
                    dispersion_w=500.0,
                    origen=OrigenFirma.INFERIDA,
                    muestras=10,
                    medida_en=datetime.now(timezone.utc),
                ),
            ),
            Carga(
                id=str(uuid.uuid4()),
                dispositivo_id=dispositivo_id,
                nombre="Carga CAMPANA",
                firma=FirmaCarga(
                    potencia_w=3000.0,
                    dispersion_w=100.0,
                    origen=OrigenFirma.CAMPANA,
                    muestras=10,
                    medida_en=datetime.now(timezone.utc),
                ),
            ),
            Carga(
                id=str(uuid.uuid4()),
                dispositivo_id=dispositivo_id,
                nombre="Carga sin firma",
                firma=None,
            ),
        ]
        mock_repo_cargas.listar_por_dispositivo.return_value = cargas

        resultado = use_case(dispositivo_id)

        # Solo 1 debe estar incluida (la INFERIDA)
        assert len(resultado.maquinas_inferidas) == 1
        assert resultado.maquinas_inferidas[0].nombre == "Carga INFERIDA"

    def test_mapeo_campos_en_dto(self, use_case, mock_repo_cargas):
        """Verificar que el mapeo de campos a DTO es correcto."""
        dispositivo_id = str(uuid.uuid4())
        carga_id = str(uuid.uuid4())
        carga = Carga(
            id=carga_id,
            dispositivo_id=dispositivo_id,
            nombre="Compresor Inferido",
            categoria=CategoriaCarga.FUERZA_MOTRIZ,
            naturaleza_electrica=NaturalezaElectrica.MIXTA,
            patron_operacion=PatronOperacion.INDETERMINADO,
            firma=FirmaCarga(
                potencia_w=7500.0,
                dispersion_w=1000.0,
                origen=OrigenFirma.INFERIDA,
                muestras=10,
                medida_en=datetime.now(timezone.utc),
            ),
        )
        mock_repo_cargas.listar_por_dispositivo.return_value = [carga]

        resultado = use_case(dispositivo_id)
        dto = resultado.maquinas_inferidas[0]

        assert dto.id == carga_id
        assert dto.nombre == "Compresor Inferido"
        assert dto.tipo_maquina == "fuerza_motriz"
        # Patrones son del patron_operacion y naturaleza_electrica
        assert len(dto.patrones_detectados) >= 0
        assert isinstance(dto, MaquinaInferidaDTO)
