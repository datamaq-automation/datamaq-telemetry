from decimal import Decimal

from sqlalchemy.orm import Session

from src.domain.telemetria.entities import (
    DispositivoLayout,
    NodoUnifilar,
    Organizacion,
    Planta,
    ZonaPlanta,
)
from src.domain.telemetria.ports import RepositorioOrganizacionesPort
from src.domain.telemetria.value_objects import (
    CoordenadasZona,
    ModoFreeTier,
    PosicionLayout,
    TipoNodoUnifilar,
)
from src.infrastructure.sqlalchemy.models import (
    FacilityDeviceLayoutModel,
    FacilityModel,
    FacilityUnifilarNodeModel,
    FacilityZoneModel,
    OrganizationModel,
)


class MySQLOrganizacionesRepository(RepositorioOrganizacionesPort):
    def __init__(self, db: Session):
        self.db = db

    def _org_to_entity(self, m: OrganizationModel) -> Organizacion:
        modo_free_vo = (
            ModoFreeTier(m.free_tier_mode)
            if m.free_tier_mode in [item.value for item in ModoFreeTier]
            else ModoFreeTier.PRIVADO_BASICO
        )
        pro_exp = m.pro_expires_at
        creado = m.created_at
        actualizado = m.updated_at

        return Organizacion(
            id=m.id,
            nombre=m.name,
            plan_id=m.plan_id,
            cuit=m.tax_id,
            email_contacto=m.contact_email,
            telefono_contacto=m.contact_phone,
            pro_vence_en=pro_exp,
            modo_free=modo_free_vo,
            creado_en=creado,
            actualizado_en=actualizado,
        )

    def obtener_por_id(self, organizacion_id: str) -> Organizacion | None:
        m = self.db.query(OrganizationModel).filter(OrganizationModel.id == organizacion_id).first()
        if not m:
            return None
        return self._org_to_entity(m)

    def listar_organizaciones(self) -> list[Organizacion]:
        models = self.db.query(OrganizationModel).all()
        return [self._org_to_entity(m) for m in models]

    def guardar_organizacion(self, org: Organizacion) -> Organizacion:
        model = self.db.query(OrganizationModel).filter(OrganizationModel.id == org.id).first()
        modo_free_str = org.modo_free.value if hasattr(org.modo_free, "value") else str(org.modo_free)
        if not model:
            model = OrganizationModel(
                id=org.id,
                name=org.nombre,
                plan_id=org.plan_id,
                tax_id=org.cuit,
                contact_email=org.email_contacto,
                contact_phone=org.telefono_contacto,
                pro_expires_at=org.pro_vence_en,
                free_tier_mode=modo_free_str,
            )
            self.db.add(model)
        else:
            model.name = org.nombre
            model.plan_id = org.plan_id
            model.tax_id = org.cuit
            model.contact_email = org.email_contacto
            model.contact_phone = org.telefono_contacto
            model.pro_expires_at = org.pro_vence_en
            model.free_tier_mode = modo_free_str

        self.db.commit()
        self.db.refresh(model)
        return self._org_to_entity(model)

    def obtener_planta_por_id(self, planta_id: str) -> Planta | None:
        m = self.db.query(FacilityModel).filter(FacilityModel.id == planta_id).first()
        if not m:
            return None
        return Planta(
            id=m.id,
            organizacion_id=m.organization_id,
            nombre=m.name,
            direccion=m.address,
            latitud=float(m.latitude) if m.latitude is not None else None,
            longitud=float(m.longitude) if m.longitude is not None else None,
            layout_svg_url=m.layout_svg_url,
            creado_en=m.created_at,
            actualizado_en=m.updated_at,
        )

    def listar_plantas(self, organizacion_id: str | None = None) -> list[Planta]:
        q = self.db.query(FacilityModel)
        if organizacion_id:
            q = q.filter(FacilityModel.organization_id == organizacion_id)
        return [
            Planta(
                id=m.id,
                organizacion_id=m.organization_id,
                nombre=m.name,
                direccion=m.address,
                latitud=float(m.latitude) if m.latitude is not None else None,
                longitud=float(m.longitude) if m.longitude is not None else None,
                layout_svg_url=m.layout_svg_url,
                creado_en=m.created_at,
                actualizado_en=m.updated_at,
            )
            for m in q.all()
        ]

    def guardar_planta(self, planta: Planta) -> Planta:
        model = self.db.query(FacilityModel).filter(FacilityModel.id == planta.id).first()
        lat_dec = Decimal(str(planta.latitud)) if planta.latitud is not None else None
        lon_dec = Decimal(str(planta.longitud)) if planta.longitud is not None else None
        if not model:
            model = FacilityModel(
                id=planta.id,
                organization_id=planta.organizacion_id,
                name=planta.nombre,
                address=planta.direccion,
                latitude=lat_dec,
                longitude=lon_dec,
                layout_svg_url=planta.layout_svg_url,
            )
            self.db.add(model)
        else:
            model.organization_id = planta.organizacion_id
            model.name = planta.nombre
            model.address = planta.direccion
            model.latitude = lat_dec
            model.longitude = lon_dec
            model.layout_svg_url = planta.layout_svg_url

        self.db.commit()
        self.db.refresh(model)
        return Planta(
            id=model.id,
            organizacion_id=model.organization_id,
            nombre=model.name,
            direccion=model.address,
            latitud=float(model.latitude) if model.latitude is not None else None,
            longitud=float(model.longitude) if model.longitude is not None else None,
            layout_svg_url=model.layout_svg_url,
            creado_en=model.created_at,
            actualizado_en=model.updated_at,
        )

    def obtener_nodos_unifilar(self, planta_id: str) -> list[NodoUnifilar]:
        models = (
            self.db.query(FacilityUnifilarNodeModel)
            .filter(FacilityUnifilarNodeModel.facility_id == planta_id)
            .order_by(FacilityUnifilarNodeModel.sort_order.asc())
            .all()
        )
        return [
            NodoUnifilar(
                id=m.id,
                planta_id=m.facility_id,
                parent_id=m.parent_id,
                nombre=m.name,
                tipo=(
                    TipoNodoUnifilar(m.node_type)
                    if m.node_type in [t.value for t in TipoNodoUnifilar]
                    else TipoNodoUnifilar.CARGA
                ),
                device_id=m.device_id,
                tension_nominal_v=float(m.nominal_voltage_v),
                capacidad_nominal_kva=float(m.nominal_capacity_kva) if m.nominal_capacity_kva is not None else None,
                orden=m.sort_order,
                creado_en=m.created_at,
                actualizado_en=m.updated_at,
            )
            for m in models
        ]

    def guardar_nodos_unifilar(self, planta_id: str, nodos: list[NodoUnifilar]) -> list[NodoUnifilar]:
        self.db.query(FacilityUnifilarNodeModel).filter(FacilityUnifilarNodeModel.facility_id == planta_id).delete()

        for nodo in nodos:
            tipo_str = nodo.tipo.value if hasattr(nodo.tipo, "value") else str(nodo.tipo)
            model = FacilityUnifilarNodeModel(
                id=nodo.id,
                facility_id=planta_id,
                parent_id=nodo.parent_id,
                name=nodo.nombre,
                node_type=tipo_str,
                device_id=nodo.device_id,
                nominal_voltage_v=Decimal(str(nodo.tension_nominal_v)),
                nominal_capacity_kva=(
                    Decimal(str(nodo.capacidad_nominal_kva)) if nodo.capacidad_nominal_kva is not None else None
                ),
                sort_order=nodo.orden,
            )
            self.db.add(model)

        self.db.commit()
        return self.obtener_nodos_unifilar(planta_id)

    def obtener_zonas_planta(self, planta_id: str) -> list[ZonaPlanta]:
        models = self.db.query(FacilityZoneModel).filter(FacilityZoneModel.facility_id == planta_id).all()
        return [
            ZonaPlanta(
                id=m.id,
                planta_id=m.facility_id,
                nombre=m.name,
                coordenadas=CoordenadasZona(
                    x_porcentaje=float(m.x_pct),
                    y_porcentaje=float(m.y_pct),
                    ancho_porcentaje=float(m.width_pct),
                    alto_porcentaje=float(m.height_pct),
                ),
                creado_en=m.created_at,
                actualizado_en=m.updated_at,
            )
            for m in models
        ]

    def obtener_dispositivos_layout(self, planta_id: str) -> list[DispositivoLayout]:
        models = (
            self.db.query(FacilityDeviceLayoutModel).filter(FacilityDeviceLayoutModel.facility_id == planta_id).all()
        )
        return [
            DispositivoLayout(
                id=m.id,
                planta_id=m.facility_id,
                device_id=m.device_id,
                zona_id=m.zone_id,
                posicion=PosicionLayout(
                    x_porcentaje=float(m.pos_x_pct),
                    y_porcentaje=float(m.pos_y_pct),
                ),
                creado_en=m.created_at,
                actualizado_en=m.updated_at,
            )
            for m in models
        ]

    def guardar_layout_planta(
        self,
        planta_id: str,
        plano_svg_url: str | None,
        zonas: list[ZonaPlanta],
        dispositivos: list[DispositivoLayout],
    ) -> None:
        planta_model = self.db.query(FacilityModel).filter(FacilityModel.id == planta_id).first()
        if planta_model:
            planta_model.layout_svg_url = plano_svg_url

        self.db.query(FacilityDeviceLayoutModel).filter(FacilityDeviceLayoutModel.facility_id == planta_id).delete()
        self.db.query(FacilityZoneModel).filter(FacilityZoneModel.facility_id == planta_id).delete()

        for z in zonas:
            zm = FacilityZoneModel(
                id=z.id,
                facility_id=planta_id,
                name=z.nombre,
                x_pct=Decimal(str(z.coordenadas.x_porcentaje)),
                y_pct=Decimal(str(z.coordenadas.y_porcentaje)),
                width_pct=Decimal(str(z.coordenadas.ancho_porcentaje)),
                height_pct=Decimal(str(z.coordenadas.alto_porcentaje)),
            )
            self.db.add(zm)

        for d in dispositivos:
            dm = FacilityDeviceLayoutModel(
                id=d.id,
                facility_id=planta_id,
                device_id=d.device_id,
                zone_id=d.zona_id,
                pos_x_pct=Decimal(str(d.posicion.x_porcentaje)),
                pos_y_pct=Decimal(str(d.posicion.y_porcentaje)),
            )
            self.db.add(dm)

        self.db.commit()
