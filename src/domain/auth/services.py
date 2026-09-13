"""src/domain/auth/services.py."""

import base64
import hashlib
import hmac
import math
import secrets
import time
from datetime import datetime, timedelta, timezone

from src.domain.auth.entities import AccesoPlantaUsuario
from src.domain.telemetria.entities import Planta


class HashContrasenaService:
    """Hashea y verifica contraseñas con scrypt (stdlib, sin dependencias)."""

    N: int = 2**14
    R: int = 8
    P: int = 1
    SALT_BYTES: int = 16
    DIGEST_BYTES: int = 32

    @classmethod
    def generar_hash(cls, contrasena: str) -> str:
        salt = secrets.token_bytes(cls.SALT_BYTES)
        digest = hashlib.scrypt(
            contrasena.encode("utf-8"),
            salt=salt,
            n=cls.N,
            r=cls.R,
            p=cls.P,
            dklen=cls.DIGEST_BYTES,
        )
        return "$".join(
            (
                "scrypt",
                str(cls.N),
                str(cls.R),
                str(cls.P),
                base64.b64encode(salt).decode("ascii"),
                base64.b64encode(digest).decode("ascii"),
            )
        )

    @classmethod
    def verificar(cls, contrasena: str, hash_almacenado: str) -> bool:
        try:
            algoritmo, n_raw, r_raw, p_raw, salt_b64, digest_b64 = hash_almacenado.split("$")
            if algoritmo != "scrypt":
                return False
            n = int(n_raw)
            r = int(r_raw)
            p = int(p_raw)
            salt = base64.b64decode(salt_b64)
            esperado = base64.b64decode(digest_b64)
        except (ValueError, TypeError):
            return False

        digest = hashlib.scrypt(
            contrasena.encode("utf-8"),
            salt=salt,
            n=n,
            r=r,
            p=p,
            dklen=len(esperado),
        )
        return hmac.compare_digest(digest, esperado)


ROLES_ACCESO_GLOBAL: frozenset[str] = frozenset({"superadmin", "invitado_global"})


class PoliticaAccesoPlantasService:
    """Decide a qué plantas accede un usuario y si puede cambiar la activa.

    Reglas, en orden:
    1. Roles globales (`superadmin`, `invitado_global`): todas las plantas de todas
       las organizaciones, siempre con permiso de cambio. La tabla de asignaciones
       no aplica para ellos.
    2. Usuario con filas explícitas en `user_facility_access`: solo esas plantas,
       acotadas a su organización (una fila que apunte a otra org se ignora), con
       el `puede_cambiar` de cada fila.
    3. Usuario sin filas: comportamiento histórico, todas las plantas de su
       organización con permiso de cambio.

    La planta activa es la primera de la lista resultante (orden de asignación
    para el caso 2, orden del YAML para los otros).
    """

    @staticmethod
    def resolver(
        rol: str,
        organizacion_id: str | None,
        plantas: list[Planta],
        accesos: list[AccesoPlantaUsuario],
    ) -> list[tuple[Planta, bool]]:
        if rol in ROLES_ACCESO_GLOBAL:
            return [(p, True) for p in plantas]
        propias = [p for p in plantas if organizacion_id is not None and p.organizacion_id == organizacion_id]
        if not accesos:
            return [(p, True) for p in propias]
        por_id = {p.id: p for p in propias}
        resultado: list[tuple[Planta, bool]] = []
        vistas: set[str] = set()
        for acceso in sorted(accesos, key=lambda a: (a.creado_en, a.planta_id)):
            planta = por_id.get(acceso.planta_id)
            if planta is None or planta.id in vistas:
                continue
            vistas.add(planta.id)
            resultado.append((planta, acceso.puede_cambiar))
        return resultado


class PoliticaExpiracionService:
    @staticmethod
    def calcular_expiracion(ahora: datetime, minutos_validez: int) -> datetime:
        return ahora + timedelta(minutes=minutos_validez)


class RateLimiterService:
    """Limita los intentos de inicio de sesión por clave dentro de una ventana deslizante."""

    MAX_CLAVES: int = 10000

    def __init__(self, max_intentos: int, ventana_segundos: int):
        self.max_intentos = max_intentos
        self.ventana_segundos = ventana_segundos
        self._intentos: dict[str, list[datetime]] = {}

    def _purgar(self, clave: str, ahora: datetime) -> None:
        limite = ahora - timedelta(seconds=self.ventana_segundos)
        self._intentos[clave] = [t for t in self._intentos.get(clave, []) if t > limite]

    def permitir(self, clave: str, max_intentos: int | None = None) -> bool:
        ahora = datetime.now(timezone.utc)
        self._purgar(clave, ahora)
        limite = max_intentos if max_intentos is not None else self.max_intentos
        return len(self._intentos.get(clave, [])) < limite

    def registrar_intento(self, clave: str) -> None:
        ahora = datetime.now(timezone.utc)
        es_nueva = clave not in self._intentos
        if es_nueva and len(self._intentos) >= self.MAX_CLAVES:
            clave_mas_antigua = min(
                (k for k, v in self._intentos.items() if v),
                key=lambda k: self._intentos[k][0],
                default=None,
            )
            if clave_mas_antigua is not None:
                self._intentos.pop(clave_mas_antigua)
        self._purgar(clave, ahora)
        self._intentos.setdefault(clave, []).append(ahora)

    def resetear(self, clave: str) -> None:
        self._intentos.pop(clave, None)

    def segundos_restantes(self, clave: str, max_intentos: int | None = None) -> int:
        """Segundos restantes de bloqueo; 0 si la clave aún está permitida."""
        ahora = datetime.now(timezone.utc)
        self._purgar(clave, ahora)
        intentos = self._intentos.get(clave, [])
        limite = max_intentos if max_intentos is not None else self.max_intentos
        if len(intentos) < limite:
            return 0
        mas_antiguo = min(intentos)
        edad = (ahora - mas_antiguo).total_seconds()
        return max(1, math.ceil(self.ventana_segundos - edad))


class TokenRevocationService:
    """Mantiene en memoria el registro de timestamps de revocación de sesiones por usuario."""

    def __init__(self, ventana_retencion_segundos: int = 7200):
        self.ventana_retencion_segundos = ventana_retencion_segundos
        self._revocaciones: dict[str, int] = {}

    def revocar_usuario(self, usuario_id: str, timestamp: int | None = None) -> None:
        ts = timestamp if timestamp is not None else int(time.time())
        self._revocaciones[usuario_id] = ts

    def esta_revocado(self, usuario_id: str, iat: int) -> bool:
        ts_revocacion = self._revocaciones.get(usuario_id)
        if ts_revocacion is None:
            return False
        return iat < ts_revocacion


class CodigosRespaldoService:
    CARACTERES_VALIDOS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

    @classmethod
    def generar_codigo(cls) -> str:
        parte1 = "".join(secrets.choice(cls.CARACTERES_VALIDOS) for _ in range(4))
        parte2 = "".join(secrets.choice(cls.CARACTERES_VALIDOS) for _ in range(4))
        return f"{parte1}-{parte2}"

    @classmethod
    def generar_codigos(cls, cantidad: int = 8) -> list[str]:
        return [cls.generar_codigo() for _ in range(cantidad)]

    @classmethod
    def normalizar(cls, codigo: str) -> str:
        return codigo.strip().upper().replace(" ", "")

    @classmethod
    def hashear(cls, codigo: str) -> str:
        return HashContrasenaService.generar_hash(cls.normalizar(codigo))

    @classmethod
    def verificar_y_consumir(cls, codigo: str, hashes: list[str]) -> tuple[bool, list[str]]:
        codigo_norm = cls.normalizar(codigo)
        for i, h in enumerate(hashes):
            if HashContrasenaService.verificar(codigo_norm, h):
                restantes = hashes[:i] + hashes[i + 1 :]
                return True, restantes
        return False, hashes


class TokenDispositivoService:
    @staticmethod
    def generar_secreto() -> str:
        return secrets.token_urlsafe(32)

    @staticmethod
    def calcular_hash(secreto: str) -> str:
        return hashlib.sha256(secreto.strip().encode("utf-8")).hexdigest()
