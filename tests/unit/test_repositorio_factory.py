"""tests/unit/test_repositorio_factory.py — Tests para Abstract Factory de Repositorios."""

from unittest.mock import MagicMock

import pytest

from src.adapters.gateways.in_memory_repository_factory import InMemoryRepositorioFactory
from src.domain.telemetria.ports import (
    RepositorioDispositivosPort,
    RepositorioFactoryPort,
    RepositorioPlanesPort,
    RepositorioSuscripcionesPort,
    RepositorioTelemetriaPort,
)
from src.infrastructure.sqlalchemy.repository_factory import SQLAlchemyRepositorioFactory


class TestSQLAlchemyRepositorioFactory:
    def test_implementa_interfaz_repositorio_factory_port(self):
        mock_session = MagicMock()
        factory = SQLAlchemyRepositorioFactory(mock_session)
        assert isinstance(factory, RepositorioFactoryPort)

    def test_crea_instancias_de_repositorios(self):
        mock_session = MagicMock()
        factory = SQLAlchemyRepositorioFactory(mock_session)

        disp_repo = factory.dispositivos()
        assert isinstance(disp_repo, RepositorioDispositivosPort)

        telem_repo = factory.telemetria()
        assert isinstance(telem_repo, RepositorioTelemetriaPort)

        sus_repo = factory.suscripciones()
        assert isinstance(sus_repo, RepositorioSuscripcionesPort)

        planes_repo = factory.planes()
        assert isinstance(planes_repo, RepositorioPlanesPort)


class TestInMemoryRepositorioFactory:
    def test_implementa_interfaz_repositorio_factory_port(self):
        factory = InMemoryRepositorioFactory()
        assert isinstance(factory, RepositorioFactoryPort)

    def test_provee_repositorios_inyectados(self):
        mock_disp = MagicMock(spec=RepositorioDispositivosPort)
        mock_telem = MagicMock(spec=RepositorioTelemetriaPort)
        mock_sus = MagicMock(spec=RepositorioSuscripcionesPort)
        mock_planes = MagicMock(spec=RepositorioPlanesPort)

        factory = InMemoryRepositorioFactory(
            dispositivos=mock_disp,
            telemetria=mock_telem,
            suscripciones=mock_sus,
            planes=mock_planes,
        )

        assert factory.dispositivos() is mock_disp
        assert factory.telemetria() is mock_telem
        assert factory.suscripciones() is mock_sus
        assert factory.planes() is mock_planes

    def test_lanza_error_cuando_no_esta_configurado(self):
        factory = InMemoryRepositorioFactory()
        with pytest.raises(NotImplementedError):
            factory.dispositivos()
        with pytest.raises(NotImplementedError):
            factory.telemetria()
        with pytest.raises(NotImplementedError):
            factory.suscripciones()
        with pytest.raises(NotImplementedError):
            factory.planes()
