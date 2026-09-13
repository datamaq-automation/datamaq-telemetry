"""src/domain/auth/entities.py."""

from dataclasses import dataclass, field
from datetime import datetime, timezone


def ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class UsuarioAuth:
    id: str
    usuario: str
    hash_contrasena: str
    esta_activo: bool = True
    rol: str = "operador"
    organizacion_id: str | None = None
    totp_secret: str | None = None
    totp_enabled: bool = False
    totp_backup_codes: list[str] | None = None
    creado_en: datetime = field(default_factory=ahora_utc)
    actualizado_en: datetime = field(default_factory=ahora_utc)


@dataclass
class DispositivoConfiable:
    id: str
    usuario_id: str
    token_hash: str
    nombre_dispositivo: str | None = None
    user_agent: str = ""
    ip_origen: str = ""
    creado_en: datetime = field(default_factory=ahora_utc)
    ultimo_acceso_en: datetime = field(default_factory=ahora_utc)
    expira_en: datetime = field(default_factory=ahora_utc)
    revocado: bool = False

    def coincide_red(self, ip: str) -> bool:
        """Valida si una IP coincide exactamente o pertenece a la misma subred (/24 en IPv4, /64 en IPv6)."""
        import ipaddress

        if not self.ip_origen or not ip:
            return False
        if self.ip_origen == ip:
            return True
        try:
            addr1 = ipaddress.ip_address(self.ip_origen)
            addr2 = ipaddress.ip_address(ip)
            if addr1.version != addr2.version:
                return False
            if addr1.version == 4:
                net1 = ipaddress.ip_network(f"{self.ip_origen}/24", strict=False)
                return addr2 in net1
            elif addr1.version == 6:
                net1 = ipaddress.ip_network(f"{self.ip_origen}/64", strict=False)
                return addr2 in net1
        except ValueError:
            return self.ip_origen == ip
        return False

    def es_valido(self, ip: str | None = None, ahora: datetime | None = None) -> bool:
        if self.revocado:
            return False
        momento = ahora if ahora is not None else ahora_utc()
        if self.expira_en <= momento:
            return False
        if ip is not None and not self.coincide_red(ip):
            return False
        return True


@dataclass
class AccesoPlantaUsuario:
    """Fila de `user_facility_access`: una planta a la que un usuario puede acceder.

    `puede_cambiar=False` significa que la planta está fija para ese usuario: el
    selector de planta del frontend se muestra bloqueado en `planta_activa_id`.
    """

    usuario_id: str
    planta_id: str
    puede_cambiar: bool = True
    creado_en: datetime = field(default_factory=ahora_utc)
