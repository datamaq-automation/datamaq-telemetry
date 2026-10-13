"""src/infrastructure/sqlalchemy/repositories/activos_unifilar_repository.py — Repositorio SQLAlchemy para ActivosUnifilar."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.domain.telemetria.entities import ActivoUnifilar
from src.domain.telemetria.ports import RepositorioActivosUnifilarPort
from src.domain.telemetria.value_objects import TipoActivoUnifilar
from src.infrastructure.sqlalchemy.activos_unifilar_models import ActivoUnifilarModel


class MySQLActivosUnifilarRepository(RepositorioActivosUnifilarPort):
    """Implementación MySQL/SQLAlchemy para la persistencia de activos unifilares mutables."""

    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def _to_entity(m: ActivoUnifilarModel) -> ActivoUnifilar:
        return ActivoUnifilar(
            id=m.id,
            planta_id=m.planta_id,
            nombre=m.nombre,
            tipo=TipoActivoUnifilar(m.tipo),
            tension_nominal_v=float(m.tension_nominal_v),
            parent_id=m.parent_id,
            device_id=m.device_id,
            potencia_nominal_kw=float(m.potencia_nominal_kw) if m.potencia_nominal_kw is not None else None,
            capacidad_nominal_kva=float(m.capacidad_nominal_kva) if m.capacidad_nominal_kva is not None else None,
            categoria_uso=m.categoria_uso,
            uso_significativo=bool(m.uso_significativo),
            posicion_x=float(m.posicion_x) if m.posicion_x is not None else None,
            posicion_y=float(m.posicion_y) if m.posicion_y is not None else None,
            ancho=float(m.ancho) if m.ancho is not None else None,
            alto=float(m.alto) if m.alto is not None else None,
            orden=int(m.orden),
            creado_en=m.creado_en,
            actualizado_en=m.actualizado_en,
        )

    def obtener_por_id(self, activo_id: str) -> ActivoUnifilar | None:
        modelo = self.db.get(ActivoUnifilarModel, activo_id)
        return self._to_entity(modelo) if modelo else None

    def listar_por_planta(self, planta_id: str) -> list[ActivoUnifilar]:
        stmt = (
            select(ActivoUnifilarModel)
            .where(ActivoUnifilarModel.planta_id == planta_id)
            .order_by(ActivoUnifilarModel.orden.asc(), ActivoUnifilarModel.nombre.asc())
        )
        modelos = self.db.execute(stmt).scalars().all()
        return [self._to_entity(m) for m in modelos]

    def guardar(self, activo: ActivoUnifilar) -> ActivoUnifilar:
        modelo = self.db.get(ActivoUnifilarModel, activo.id)
        tipo_str = activo.tipo.value if hasattr(activo.tipo, "value") else str(activo.tipo)
        if modelo:
            modelo.nombre = activo.nombre
            modelo.tipo = tipo_str
            modelo.parent_id = activo.parent_id
            modelo.device_id = activo.device_id
            modelo.tension_nominal_v = activo.tension_nominal_v
            modelo.potencia_nominal_kw = activo.potencia_nominal_kw
            modelo.capacidad_nominal_kva = activo.capacidad_nominal_kva
            modelo.categoria_uso = activo.categoria_uso
            modelo.uso_significativo = activo.uso_significativo
            modelo.posicion_x = activo.posicion_x
            modelo.posicion_y = activo.posicion_y
            modelo.ancho = activo.ancho
            modelo.alto = activo.alto
            modelo.orden = activo.orden
            modelo.actualizado_en = activo.actualizado_en
        else:
            modelo = ActivoUnifilarModel(
                id=activo.id,
                planta_id=activo.planta_id,
                nombre=activo.nombre,
                tipo=tipo_str,
                parent_id=activo.parent_id,
                device_id=activo.device_id,
                tension_nominal_v=activo.tension_nominal_v,
                potencia_nominal_kw=activo.potencia_nominal_kw,
                capacidad_nominal_kva=activo.capacidad_nominal_kva,
                categoria_uso=activo.categoria_uso,
                uso_significativo=activo.uso_significativo,
                posicion_x=activo.posicion_x,
                posicion_y=activo.posicion_y,
                ancho=activo.ancho,
                alto=activo.alto,
                orden=activo.orden,
                creado_en=activo.creado_en,
                actualizado_en=activo.actualizado_en,
            )
            self.db.add(modelo)
        self.db.flush()
        return self._to_entity(modelo)

    def guardar_lote(self, activos: list[ActivoUnifilar]) -> list[ActivoUnifilar]:
        return [self.guardar(a) for a in activos]

    def eliminar(self, activo_id: str) -> bool:
        modelo = self.db.get(ActivoUnifilarModel, activo_id)
        if not modelo:
            return False
        self.db.delete(modelo)
        self.db.flush()
        return True
