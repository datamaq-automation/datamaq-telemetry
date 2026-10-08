"""Repositorio SQLAlchemy de validaciones OTP y auditoría del cambio de contraseña."""

from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.domain.auth.entities import ValidacionCambioContrasena
from src.domain.auth.ports import RepositorioCambioContrasenaPort
from src.infrastructure.sqlalchemy.models import AuditoriaChangeContraseniaModel, CambioContraseniaValidacionModel


def _a_entidad(model: CambioContraseniaValidacionModel) -> ValidacionCambioContrasena:
    return ValidacionCambioContrasena(
        id=model.id,
        usuario_id=model.usuario_id,
        codigo_hash=model.codigo_hash,
        ttl_expira=model.ttl_expira,
        creado_en=model.creado_en,
        intentos_fallidos=model.intentos_fallidos,
        consumido_en=model.consumido_en,
    )


class MySQLCambioContrasenaRepository(RepositorioCambioContrasenaPort):
    def __init__(self, db: Session):
        self.db = db

    def crear_validacion(
        self, usuario_id: str, codigo_hash: str, ttl_expira: datetime, ahora: datetime
    ) -> ValidacionCambioContrasena:
        model = CambioContraseniaValidacionModel(
            usuario_id=usuario_id,
            codigo_hash=codigo_hash,
            intentos_fallidos=0,
            ttl_expira=ttl_expira,
            creado_en=ahora,
        )
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return _a_entidad(model)

    def invalidar_vigentes(self, usuario_id: str, ahora: datetime) -> None:
        (
            self.db.query(CambioContraseniaValidacionModel)
            .filter(
                CambioContraseniaValidacionModel.usuario_id == usuario_id,
                CambioContraseniaValidacionModel.consumido_en.is_(None),
            )
            .update({"consumido_en": ahora}, synchronize_session=False)
        )
        self.db.commit()

    def contar_solicitudes_desde(self, usuario_id: str, desde: datetime) -> int:
        return (
            self.db.query(func.count(CambioContraseniaValidacionModel.id))
            .filter(
                CambioContraseniaValidacionModel.usuario_id == usuario_id,
                CambioContraseniaValidacionModel.creado_en >= desde,
            )
            .scalar()
            or 0
        )

    def obtener_vigente(self, usuario_id: str, ahora: datetime) -> ValidacionCambioContrasena | None:
        model = (
            self.db.query(CambioContraseniaValidacionModel)
            .filter(
                CambioContraseniaValidacionModel.usuario_id == usuario_id,
                CambioContraseniaValidacionModel.consumido_en.is_(None),
                CambioContraseniaValidacionModel.ttl_expira > ahora,
            )
            .order_by(CambioContraseniaValidacionModel.creado_en.desc(), CambioContraseniaValidacionModel.id.desc())
            .first()
        )
        return _a_entidad(model) if model else None

    def registrar_intento_fallido(self, validacion_id: int) -> int:
        model = self.db.get(CambioContraseniaValidacionModel, validacion_id)
        if model is None:
            raise ValueError(f"Validación de cambio de contraseña inexistente: {validacion_id}")
        model.intentos_fallidos += 1
        self.db.commit()
        return model.intentos_fallidos

    def consumir(self, validacion_id: int, ahora: datetime) -> None:
        model = self.db.get(CambioContraseniaValidacionModel, validacion_id)
        if model is None:
            raise ValueError(f"Validación de cambio de contraseña inexistente: {validacion_id}")
        model.consumido_en = ahora
        self.db.commit()

    def registrar_auditoria(
        self, usuario_id: str, estado: str, ip: str | None, user_agent: str | None, ahora: datetime
    ) -> None:
        self.db.add(
            AuditoriaChangeContraseniaModel(
                usuario_id=usuario_id,
                ip=ip,
                user_agent=(user_agent or "")[:255] or None,
                estado=estado,
                creado_en=ahora,
            )
        )
        self.db.commit()
