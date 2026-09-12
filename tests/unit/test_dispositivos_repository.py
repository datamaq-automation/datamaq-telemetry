"""tests/unit/test_dispositivos_repository.py — Tests unitarios para MySQLDispositivosRepository con Mocks de Session."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from src.domain.telemetria.entities import Dispositivo
from src.domain.telemetria.value_objects import EstadoDispositivo, MacAddress
from src.infrastructure.sqlalchemy.models import DeviceModel, FacilityModel
from src.infrastructure.sqlalchemy.repositories.dispositivos_repository import (
    MySQLDispositivosRepository,
)

PLANTA_ID = "fac-001"
ORG_ID = "org-001"
DEVICE_ID = "dev-001"
MAC_STR = "AABBCCDDEEFF"


def _crear_device_model(
    *,
    id: str = DEVICE_ID,
    facility_id: str | None = PLANTA_ID,
    device_uid: str = MAC_STR,
    serial_number: str | None = "SN-12345",
    name: str = "Medidor Principal",
    model: str = "SmartPlus",
    hw_version: str | None = "v2.0",
    fw_version: str | None = "v1.2.3",
    tag_location: str | None = "Tablero General",
    esta_activo: bool = True,
    estado: str = "ONLINE",
    last_seen_at: datetime | None = None,
    installation_type: str = "CONSUMO",
    phases_with_ct: str = "R,S,T",
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
) -> DeviceModel:
    now = datetime.now(timezone.utc)
    return DeviceModel(
        id=id,
        facility_id=facility_id,
        device_uid=device_uid,
        serial_number=serial_number,
        name=name,
        model=model,
        hw_version=hw_version,
        fw_version=fw_version,
        tag_location=tag_location,
        esta_activo=esta_activo,
        estado=estado,
        last_seen_at=last_seen_at or now,
        installation_type=installation_type,
        phases_with_ct=phases_with_ct,
        created_at=created_at or now,
        updated_at=updated_at or now,
    )


def _crear_dispositivo(
    *,
    id: str = DEVICE_ID,
    planta_id: str | None = PLANTA_ID,
    device_uid: str = MAC_STR,
    numero_serie: str | None = "SN-12345",
    nombre: str = "Medidor Principal",
    modelo: str = "SmartPlus",
    version_hw: str | None = "v2.0",
    version_fw: str | None = "v1.2.3",
    ubicacion_tag: str | None = "Tablero General",
    esta_activo: bool = True,
    estado: EstadoDispositivo = EstadoDispositivo.ONLINE,
    visto_por_ultima_vez: datetime | None = None,
    tipo_instalacion: str = "CONSUMO",
    fases_con_ti: str = "R,S,T",
) -> Dispositivo:
    return Dispositivo(
        id=id,
        device_uid=MacAddress(device_uid),
        nombre=nombre,
        modelo=modelo,
        planta_id=planta_id,
        numero_serie=numero_serie,
        version_hw=version_hw,
        version_fw=version_fw,
        ubicacion_tag=ubicacion_tag,
        esta_activo=esta_activo,
        estado=estado,
        visto_por_ultima_vez=visto_por_ultima_vez,
        tipo_instalacion=tipo_instalacion,
        fases_con_ti=fases_con_ti,
    )


@pytest.fixture
def mock_db() -> tuple[MagicMock, MagicMock]:
    """Crea un mock de Session de SQLAlchemy con soporte para method chaining de consultas."""
    session = MagicMock(spec=Session)
    query = MagicMock()
    session.query.return_value = query
    query.filter.return_value = query
    query.join.return_value = query
    return session, query


class TestMySQLDispositivosRepositoryObtener:
    def test_obtener_por_id_existente(self, mock_db: tuple[MagicMock, MagicMock]):
        session, query = mock_db
        repo = MySQLDispositivosRepository(session)
        model = _crear_device_model(id="dev-42", name="Transformador A")
        query.first.return_value = model

        resultado = repo.obtener_por_id("dev-42")

        session.query.assert_called_once_with(DeviceModel)
        query.first.assert_called_once()
        assert query.filter.call_count == 1
        filter_expr = query.filter.call_args[0][0]
        assert filter_expr.compare(DeviceModel.id == "dev-42")

        assert resultado is not None
        assert resultado.id == "dev-42"
        assert resultado.nombre == "Transformador A"
        assert resultado.device_uid == MacAddress(MAC_STR)
        assert resultado.estado == EstadoDispositivo.ONLINE

    def test_obtener_por_id_inexistente_retorna_none(self, mock_db: tuple[MagicMock, MagicMock]):
        session, query = mock_db
        repo = MySQLDispositivosRepository(session)
        query.first.return_value = None

        resultado = repo.obtener_por_id("dev-inexistente")

        session.query.assert_called_once_with(DeviceModel)
        assert query.filter.call_count == 1
        filter_expr = query.filter.call_args[0][0]
        assert filter_expr.compare(DeviceModel.id == "dev-inexistente")
        assert resultado is None

    def test_obtener_por_uid_existente(self, mock_db: tuple[MagicMock, MagicMock]):
        session, query = mock_db
        repo = MySQLDispositivosRepository(session)
        uid = MacAddress("AA:BB:CC:DD:EE:01")
        model = _crear_device_model(device_uid=uid.valor, name="Medidor Tablero 2")
        query.first.return_value = model

        resultado = repo.obtener_por_uid(uid)

        session.query.assert_called_once_with(DeviceModel)
        assert query.filter.call_count == 1
        filter_expr = query.filter.call_args[0][0]
        assert filter_expr.compare(DeviceModel.device_uid == uid.valor)

        assert resultado is not None
        assert resultado.id == DEVICE_ID
        assert resultado.device_uid == uid
        assert resultado.nombre == "Medidor Tablero 2"

    def test_obtener_por_uid_inexistente_retorna_none(self, mock_db: tuple[MagicMock, MagicMock]):
        session, query = mock_db
        repo = MySQLDispositivosRepository(session)
        uid = MacAddress("11:22:33:44:55:66")
        query.first.return_value = None

        resultado = repo.obtener_por_uid(uid)

        session.query.assert_called_once_with(DeviceModel)
        assert query.filter.call_count == 1
        filter_expr = query.filter.call_args[0][0]
        assert filter_expr.compare(DeviceModel.device_uid == uid.valor)
        assert resultado is None


class TestMySQLDispositivosRepositoryListar:
    def test_listar_sin_filtros(self, mock_db: tuple[MagicMock, MagicMock]):
        session, query = mock_db
        repo = MySQLDispositivosRepository(session)
        model1 = _crear_device_model(id="dev-1", name="Disp 1")
        model2 = _crear_device_model(id="dev-2", name="Disp 2")
        query.all.return_value = [model1, model2]

        resultado = repo.listar()

        session.query.assert_called_once_with(DeviceModel)
        query.join.assert_not_called()
        query.filter.assert_not_called()
        query.all.assert_called_once()
        assert len(resultado) == 2
        assert [d.id for d in resultado] == ["dev-1", "dev-2"]

    def test_listar_con_planta_id(self, mock_db: tuple[MagicMock, MagicMock]):
        session, query = mock_db
        repo = MySQLDispositivosRepository(session)
        model = _crear_device_model(id="dev-1", facility_id="planta-abc")
        query.all.return_value = [model]

        resultado = repo.listar(planta_id="planta-abc")

        session.query.assert_called_once_with(DeviceModel)
        query.join.assert_not_called()
        assert query.filter.call_count == 1
        filter_expr = query.filter.call_args[0][0]
        assert filter_expr.compare(DeviceModel.facility_id == "planta-abc")
        query.all.assert_called_once()
        assert len(resultado) == 1
        assert resultado[0].planta_id == "planta-abc"

    def test_listar_con_organizacion_id(self, mock_db: tuple[MagicMock, MagicMock]):
        session, query = mock_db
        repo = MySQLDispositivosRepository(session)
        model = _crear_device_model(id="dev-1")
        query.all.return_value = [model]

        resultado = repo.listar(organizacion_id="org-xyz")

        session.query.assert_called_once_with(DeviceModel)
        query.join.assert_called_once()
        join_target, join_condition = query.join.call_args[0]
        assert join_target is FacilityModel
        assert join_condition.compare(DeviceModel.facility_id == FacilityModel.id)

        assert query.filter.call_count == 1
        filter_expr = query.filter.call_args[0][0]
        assert filter_expr.compare(FacilityModel.organization_id == "org-xyz")

        query.all.assert_called_once()
        assert len(resultado) == 1
        assert resultado[0].id == "dev-1"

    def test_listar_con_planta_y_organizacion_id(self, mock_db: tuple[MagicMock, MagicMock]):
        session, query = mock_db
        repo = MySQLDispositivosRepository(session)
        model = _crear_device_model(id="dev-1", facility_id="planta-abc")
        query.all.return_value = [model]

        resultado = repo.listar(planta_id="planta-abc", organizacion_id="org-xyz")

        session.query.assert_called_once_with(DeviceModel)
        query.join.assert_called_once()
        join_target, join_condition = query.join.call_args[0]
        assert join_target is FacilityModel
        assert join_condition.compare(DeviceModel.facility_id == FacilityModel.id)

        assert query.filter.call_count == 2
        filter_org = query.filter.call_args_list[0][0][0]
        filter_planta = query.filter.call_args_list[1][0][0]
        assert filter_org.compare(FacilityModel.organization_id == "org-xyz")
        assert filter_planta.compare(DeviceModel.facility_id == "planta-abc")

        query.all.assert_called_once()
        assert len(resultado) == 1
        assert resultado[0].id == "dev-1"

    def test_listar_vacio(self, mock_db: tuple[MagicMock, MagicMock]):
        session, query = mock_db
        repo = MySQLDispositivosRepository(session)
        query.all.return_value = []

        resultado = repo.listar()

        assert resultado == []


class TestMySQLDispositivosRepositoryContar:
    def test_contar_por_organizacion(self, mock_db: tuple[MagicMock, MagicMock]):
        session, query = mock_db
        repo = MySQLDispositivosRepository(session)
        query.count.return_value = 7

        total = repo.contar_por_organizacion("org-demo")

        session.query.assert_called_once_with(DeviceModel)
        query.join.assert_called_once()
        join_target, join_condition = query.join.call_args[0]
        assert join_target is FacilityModel
        assert join_condition.compare(DeviceModel.facility_id == FacilityModel.id)

        assert query.filter.call_count == 1
        filter_expr = query.filter.call_args[0][0]
        assert filter_expr.compare(FacilityModel.organization_id == "org-demo")

        query.count.assert_called_once()
        assert total == 7


class TestMySQLDispositivosRepositoryGuardar:
    def test_guardar_nuevo_dispositivo_crea_y_persiste(self, mock_db: tuple[MagicMock, MagicMock]):
        session, query = mock_db
        repo = MySQLDispositivosRepository(session)
        query.first.return_value = None

        ahora = datetime.now(timezone.utc)
        dispositivo = _crear_dispositivo(
            id="dev-nuevo",
            planta_id="fac-99",
            device_uid="112233445566",
            numero_serie="SN-999",
            nombre="Dispositivo Nuevo",
            modelo="SmartPlus",
            version_hw="hw-1.0",
            version_fw="fw-2.0",
            ubicacion_tag="Sector A",
            esta_activo=True,
            estado=EstadoDispositivo.ONLINE,
            visto_por_ultima_vez=ahora,
            tipo_instalacion="GENERACION",
            fases_con_ti="R,S",
        )

        resultado = repo.guardar(dispositivo)

        session.query.assert_called_once_with(DeviceModel)
        assert query.filter.call_count == 1
        filter_expr = query.filter.call_args[0][0]
        assert filter_expr.compare(DeviceModel.id == "dev-nuevo")

        session.add.assert_called_once()
        added_model: DeviceModel = session.add.call_args[0][0]
        assert isinstance(added_model, DeviceModel)
        assert added_model.id == "dev-nuevo"
        assert added_model.facility_id == "fac-99"
        assert added_model.device_uid == "112233445566"
        assert added_model.serial_number == "SN-999"
        assert added_model.name == "Dispositivo Nuevo"
        assert added_model.model == "SmartPlus"
        assert added_model.hw_version == "hw-1.0"
        assert added_model.fw_version == "fw-2.0"
        assert added_model.tag_location == "Sector A"
        assert added_model.esta_activo is True
        assert added_model.estado == "ONLINE"
        assert added_model.last_seen_at == ahora
        assert added_model.installation_type == "GENERACION"
        assert added_model.phases_with_ct == "R,S"

        session.commit.assert_called_once()
        session.refresh.assert_called_once_with(added_model)

        assert resultado.id == "dev-nuevo"
        assert resultado.nombre == "Dispositivo Nuevo"
        assert resultado.tipo_instalacion == "GENERACION"
        assert resultado.fases_con_ti == "R,S"

    def test_guardar_dispositivo_existente_actualiza_campos(self, mock_db: tuple[MagicMock, MagicMock]):
        session, query = mock_db
        repo = MySQLDispositivosRepository(session)

        model_existente = _crear_device_model(
            id="dev-existente",
            facility_id="planta-vieja",
            name="Nombre Viejo",
            model="Modelo Viejo",
            serial_number="SN-VIEJO",
            hw_version="hw-old",
            fw_version="fw-old",
            tag_location="Tag Viejo",
            esta_activo=False,
            estado="OFFLINE",
            installation_type="CONSUMO",
            phases_with_ct="R",
        )
        query.first.return_value = model_existente

        nuevo_timestamp = datetime.now(timezone.utc)
        dispositivo_actualizado = _crear_dispositivo(
            id="dev-existente",
            planta_id="planta-nueva",
            device_uid=MAC_STR,
            numero_serie="SN-NUEVO",
            nombre="Nombre Nuevo",
            modelo="Modelo Nuevo",
            version_hw="hw-new",
            version_fw="fw-new",
            ubicacion_tag="Tag Nuevo",
            esta_activo=True,
            estado=EstadoDispositivo.ONLINE,
            visto_por_ultima_vez=nuevo_timestamp,
            tipo_instalacion="GENERACION",
            fases_con_ti="R,S,T",
        )

        resultado = repo.guardar(dispositivo_actualizado)

        session.query.assert_called_once_with(DeviceModel)
        session.add.assert_not_called()

        assert model_existente.name == "Nombre Nuevo"
        assert model_existente.facility_id == "planta-nueva"
        assert model_existente.model == "Modelo Nuevo"
        assert model_existente.serial_number == "SN-NUEVO"
        assert model_existente.hw_version == "hw-new"
        assert model_existente.fw_version == "fw-new"
        assert model_existente.tag_location == "Tag Nuevo"
        assert model_existente.esta_activo is True
        assert model_existente.estado == "ONLINE"
        assert model_existente.last_seen_at == nuevo_timestamp
        assert model_existente.installation_type == "GENERACION"
        assert model_existente.phases_with_ct == "R,S,T"

        session.commit.assert_called_once()
        session.refresh.assert_called_once_with(model_existente)
        assert resultado.id == "dev-existente"
        assert resultado.nombre == "Nombre Nuevo"
        assert resultado.estado == EstadoDispositivo.ONLINE


class TestMySQLDispositivosRepositoryHeartbeat:
    def test_actualizar_heartbeat_dispositivo_inexistente_no_hace_nada(self, mock_db: tuple[MagicMock, MagicMock]):
        session, query = mock_db
        repo = MySQLDispositivosRepository(session)
        query.first.return_value = None

        repo.actualizar_heartbeat(
            dispositivo_id="dev-fantasma",
            estado=EstadoDispositivo.ONLINE,
            visto_por_ultima_vez=datetime.now(timezone.utc),
        )

        session.query.assert_called_once_with(DeviceModel)
        assert query.filter.call_count == 1
        filter_expr = query.filter.call_args[0][0]
        assert filter_expr.compare(DeviceModel.id == "dev-fantasma")
        session.commit.assert_not_called()

    def test_actualizar_heartbeat_basico_actualiza_estado_y_timestamp(self, mock_db: tuple[MagicMock, MagicMock]):
        session, query = mock_db
        repo = MySQLDispositivosRepository(session)
        model = _crear_device_model(
            id="dev-hb",
            estado="OFFLINE",
            serial_number="SN-ORIGINAL",
            fw_version="fw-orig",
            hw_version="hw-orig",
        )
        query.first.return_value = model

        nuevo_timestamp = datetime(2026, 9, 12, 10, 30, 0, tzinfo=timezone.utc)
        repo.actualizar_heartbeat(
            dispositivo_id="dev-hb",
            estado=EstadoDispositivo.ONLINE,
            visto_por_ultima_vez=nuevo_timestamp,
        )

        session.query.assert_called_once_with(DeviceModel)
        assert model.estado == "ONLINE"
        assert model.last_seen_at == nuevo_timestamp
        # Los atributos opcionales no se modifican cuando son None
        assert model.serial_number == "SN-ORIGINAL"
        assert model.fw_version == "fw-orig"
        assert model.hw_version == "hw-orig"
        session.commit.assert_called_once()

    def test_actualizar_heartbeat_completo_actualiza_versiones_y_serie(self, mock_db: tuple[MagicMock, MagicMock]):
        session, query = mock_db
        repo = MySQLDispositivosRepository(session)
        model = _crear_device_model(
            id="dev-hb-full",
            estado="OFFLINE",
            serial_number="SN-OLD",
            fw_version="fw-old",
            hw_version="hw-old",
        )
        query.first.return_value = model

        nuevo_timestamp = datetime(2026, 9, 12, 12, 0, 0, tzinfo=timezone.utc)
        repo.actualizar_heartbeat(
            dispositivo_id="dev-hb-full",
            estado=EstadoDispositivo.WARNING,
            visto_por_ultima_vez=nuevo_timestamp,
            numero_serie="SN-ACTUALIZADO",
            version_fw="fw-v3.0",
            version_hw="hw-v2.0",
        )

        assert model.estado == "WARNING"
        assert model.last_seen_at == nuevo_timestamp
        assert model.serial_number == "SN-ACTUALIZADO"
        assert model.fw_version == "fw-v3.0"
        assert model.hw_version == "hw-v2.0"
        session.commit.assert_called_once()

    @pytest.mark.parametrize(
        ("numero_serie", "version_fw", "version_hw"),
        [
            ("SN-SOLO-SERIE", None, None),
            (None, "fw-SOLO-FW", None),
            (None, None, "hw-SOLO-HW"),
        ],
    )
    def test_actualizar_heartbeat_parcial_campos_individuales(
        self,
        mock_db: tuple[MagicMock, MagicMock],
        numero_serie: str | None,
        version_fw: str | None,
        version_hw: str | None,
    ):
        session, query = mock_db
        repo = MySQLDispositivosRepository(session)
        model = _crear_device_model(
            id="dev-parcial",
            serial_number="SN-BASE",
            fw_version="fw-BASE",
            hw_version="hw-BASE",
        )
        query.first.return_value = model
        ts = datetime.now(timezone.utc)

        repo.actualizar_heartbeat(
            dispositivo_id="dev-parcial",
            estado=EstadoDispositivo.ONLINE,
            visto_por_ultima_vez=ts,
            numero_serie=numero_serie,
            version_fw=version_fw,
            version_hw=version_hw,
        )

        if numero_serie:
            assert model.serial_number == numero_serie
        else:
            assert model.serial_number == "SN-BASE"

        if version_fw:
            assert model.fw_version == version_fw
        else:
            assert model.fw_version == "fw-BASE"

        if version_hw:
            assert model.hw_version == version_hw
        else:
            assert model.hw_version == "hw-BASE"

        session.commit.assert_called_once()


class TestMySQLDispositivosRepositoryToEntity:
    def test_to_entity_mapea_todos_los_campos(self, mock_db: tuple[MagicMock, MagicMock]):
        session, _ = mock_db
        repo = MySQLDispositivosRepository(session)
        ts = datetime(2026, 9, 12, 8, 0, 0, tzinfo=timezone.utc)
        model = _crear_device_model(
            id="dev-entity",
            facility_id="fac-77",
            device_uid="AABBCCDDEEFF",
            serial_number="SN-77",
            name="Medidor Totalizador",
            model="SmartPlus-Max",
            hw_version="v3.0",
            fw_version="v2.1",
            tag_location="Sala de Bombas",
            esta_activo=True,
            estado="ONLINE",
            last_seen_at=ts,
            installation_type="GENERACION",
            phases_with_ct="R,T",
            created_at=ts,
            updated_at=ts,
        )

        entidad = repo._to_entity(model)

        assert entidad.id == "dev-entity"
        assert entidad.planta_id == "fac-77"
        assert entidad.device_uid == MacAddress("AABBCCDDEEFF")
        assert entidad.numero_serie == "SN-77"
        assert entidad.nombre == "Medidor Totalizador"
        assert entidad.modelo == "SmartPlus-Max"
        assert entidad.version_hw == "v3.0"
        assert entidad.version_fw == "v2.1"
        assert entidad.ubicacion_tag == "Sala de Bombas"
        assert entidad.esta_activo is True
        assert entidad.estado == EstadoDispositivo.ONLINE
        assert entidad.visto_por_ultima_vez == ts
        assert entidad.tipo_instalacion == "GENERACION"
        assert entidad.fases_con_ti == "R,T"
        assert entidad.creado_en == ts
        assert entidad.actualizado_en == ts

    def test_to_entity_estado_desconocido_defaultea_a_offline(self, mock_db: tuple[MagicMock, MagicMock]):
        session, _ = mock_db
        repo = MySQLDispositivosRepository(session)
        model = _crear_device_model(estado="ESTADO_INEXISTENTE")

        entidad = repo._to_entity(model)

        assert entidad.estado == EstadoDispositivo.OFFLINE

    def test_to_entity_valores_nulos_usan_defaults(self, mock_db: tuple[MagicMock, MagicMock]):
        session, _ = mock_db
        repo = MySQLDispositivosRepository(session)
        model = _crear_device_model()
        model.installation_type = None  # type: ignore[assignment]
        model.phases_with_ct = None  # type: ignore[assignment]

        entidad = repo._to_entity(model)

        assert entidad.tipo_instalacion == "CONSUMO"
        assert entidad.fases_con_ti == "R,S,T"

    def test_to_entity_atributos_ausentes_usan_defaults(self, mock_db: tuple[MagicMock, MagicMock]):
        session, _ = mock_db
        repo = MySQLDispositivosRepository(session)
        mock_model = MagicMock(spec=DeviceModel)
        mock_model.id = "dev-mock"
        mock_model.device_uid = "AABBCCDDEEFF"
        mock_model.name = "Mock Dev"
        mock_model.model = "SmartPlus"
        mock_model.facility_id = "fac-1"
        mock_model.serial_number = None
        mock_model.hw_version = None
        mock_model.fw_version = None
        mock_model.tag_location = None
        mock_model.esta_activo = True
        mock_model.estado = "WARNING"
        mock_model.last_seen_at = None
        mock_model.created_at = None
        mock_model.updated_at = None
        del mock_model.installation_type
        del mock_model.phases_with_ct

        entidad = repo._to_entity(mock_model)

        assert entidad.estado == EstadoDispositivo.WARNING
        assert entidad.tipo_instalacion == "CONSUMO"
        assert entidad.fases_con_ti == "R,S,T"
