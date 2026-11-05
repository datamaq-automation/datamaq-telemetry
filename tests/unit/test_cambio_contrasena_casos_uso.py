"""tests/unit/test_cambio_contrasena_casos_uso.py.

Casos de uso del cambio de contraseña autenticado (spec: cambio-contrasena-validado).

Fakes en memoria: el repositorio de validaciones, de usuarios y el email se simulan; la lógica
de HMAC, política, límites y revocación de sesiones corre real.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import pytest

from src.application.use_cases.cambio_contrasena import (
    ConfirmarCambioContrasenaUseCase,
    SolicitarCambioContrasenaUseCase,
)
from src.domain.auth.entities import UsuarioAuth, ValidacionCambioContrasena
from src.domain.auth.exceptions import (
    CodigoCambioInvalidoError,
    ContrasenaDebilError,
    CredencialesInvalidasError,
    DemasiadosIntentosError,
    NoSePudoEnviarCodigoError,
)
from src.domain.auth.services import HashContrasenaService
from src.domain.usuarios.servicios_contrasena import GeneradorCodigoOTP

CLAVE = "clave-otp-de-prueba-0123456789"
PASSWORD_ACTUAL = "ActualPass1"
PASSWORD_NUEVA = "NuevaPass22"
AHORA = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)


@dataclass
class RepoValidacionesFake:
    validaciones: list[ValidacionCambioContrasena] = field(default_factory=list)
    auditoria: list[tuple[str, str | None]] = field(default_factory=list)
    auditoria_detalle: list[tuple[str, str, datetime]] = field(default_factory=list)
    _seq: int = 0

    def crear_validacion(self, usuario_id, codigo_hash, ttl_expira, ahora):
        self._seq += 1
        v = ValidacionCambioContrasena(
            id=self._seq, usuario_id=usuario_id, codigo_hash=codigo_hash, ttl_expira=ttl_expira, creado_en=ahora
        )
        self.validaciones.append(v)
        return v

    def invalidar_vigentes(self, usuario_id, ahora):
        for v in self.validaciones:
            if v.usuario_id == usuario_id and v.consumido_en is None:
                v.consumido_en = ahora

    def contar_solicitudes_desde(self, usuario_id, desde):
        return sum(1 for v in self.validaciones if v.usuario_id == usuario_id and v.creado_en >= desde)

    def obtener_vigente(self, usuario_id, ahora):
        candidatas = [
            v
            for v in self.validaciones
            if v.usuario_id == usuario_id and v.consumido_en is None and v.ttl_expira > ahora
        ]
        return max(candidatas, key=lambda v: v.creado_en, default=None)

    def registrar_intento_fallido(self, validacion_id):
        v = next(v for v in self.validaciones if v.id == validacion_id)
        v.intentos_fallidos += 1
        return v.intentos_fallidos

    def consumir(self, validacion_id, ahora):
        next(v for v in self.validaciones if v.id == validacion_id).consumido_en = ahora

    def registrar_auditoria(self, usuario_id, estado, ip, user_agent, ahora):
        self.auditoria.append((estado, ip))
        self.auditoria_detalle.append((usuario_id, estado, ahora))

    def contar_auditoria_desde(self, usuario_id, estado, desde):
        return sum(1 for u, e, t in self.auditoria_detalle if u == usuario_id and e == estado and t >= desde)


class UsuariosFake:
    def __init__(self, usuario: UsuarioAuth):
        self.usuario = usuario

    def obtener_por_id(self, usuario_id):
        return self.usuario if self.usuario.id == usuario_id else None

    def guardar(self, usuario):
        self.usuario = usuario
        return usuario


class EmailFake:
    def __init__(self, ok: bool = True):
        self.ok = ok
        self.codigos: list[tuple[str, str]] = []
        self.confirmaciones: list[tuple[str, datetime, str | None]] = []

    def enviar_codigo_cambio_contrasena(self, destinatario, codigo):
        self.codigos.append((destinatario, codigo))
        return self.ok

    def notificar_cambio_contrasena(self, destinatario, momento, ip):
        self.confirmaciones.append((destinatario, momento, ip))
        return True


class CodigoFijo:
    """Reemplaza el generador aleatorio por un código conocido en los tests."""

    def __init__(self, codigo: str):
        self.codigo = codigo

    def generar(self):
        return self.codigo

    def calcular_hmac(self, codigo, clave):
        return GeneradorCodigoOTP.calcular_hmac(codigo, clave)

    def verificar(self, codigo, hash_guardado, clave):
        return GeneradorCodigoOTP.verificar(codigo, hash_guardado, clave)


def _usuario() -> UsuarioAuth:
    return UsuarioAuth(
        id="u-1",
        usuario="operador@example.com",
        hash_contrasena=HashContrasenaService.generar_hash(PASSWORD_ACTUAL),
    )


def _solicitar(repo, usuarios, email, codigo="4273", ahora=AHORA):
    caso = SolicitarCambioContrasenaUseCase(
        repo=repo,
        usuarios=usuarios,
        hash_service=HashContrasenaService,
        email=email,
        clave_otp=CLAVE,
        codigo_service=CodigoFijo(codigo),
        ahora=lambda: ahora,
    )
    return caso


def _confirmar(repo, usuarios, email, ahora=AHORA):
    return ConfirmarCambioContrasenaUseCase(
        repo=repo,
        usuarios=usuarios,
        hash_service=HashContrasenaService,
        email=email,
        clave_otp=CLAVE,
        codigo_service=CodigoFijo("0000"),
        ahora=lambda: ahora,
    )


@pytest.fixture()
def escenario():
    usuario = _usuario()
    return RepoValidacionesFake(), UsuariosFake(usuario), EmailFake()


# --- Solicitar código ---


def test_solicitar_envia_codigo_y_guarda_solo_el_hmac(escenario):
    repo, usuarios, email = escenario
    resultado = _solicitar(repo, usuarios, email).ejecutar("u-1", PASSWORD_ACTUAL, "10.0.0.1", "ua")

    assert email.codigos == [("operador@example.com", "4273")]
    assert len(repo.validaciones) == 1
    guardada = repo.validaciones[0]
    assert guardada.codigo_hash == GeneradorCodigoOTP.calcular_hmac("4273", CLAVE)
    assert "4273" not in guardada.codigo_hash
    assert guardada.ttl_expira == AHORA + timedelta(minutes=10)
    assert resultado.email_destino == "ope...@example.com"
    assert ("codigo_solicitado", "10.0.0.1") in repo.auditoria


def test_password_actual_incorrecta_da_401_sin_enviar_ni_crear(escenario):
    repo, usuarios, email = escenario
    with pytest.raises(CredencialesInvalidasError):
        _solicitar(repo, usuarios, email).ejecutar("u-1", "Incorrecta1", "10.0.0.1", "ua")
    assert email.codigos == []
    assert repo.validaciones == []
    assert ("intento_fallido", "10.0.0.1") in repo.auditoria


def test_quinta_solicitud_ok_sexta_da_429(escenario):
    repo, usuarios, email = escenario
    caso = _solicitar(repo, usuarios, email)
    for _ in range(5):
        caso.ejecutar("u-1", PASSWORD_ACTUAL, None, None)
    with pytest.raises(DemasiadosIntentosError):
        caso.ejecutar("u-1", PASSWORD_ACTUAL, None, None)
    assert len(repo.validaciones) == 5


def test_solicitudes_fuera_de_la_ventana_no_cuentan(escenario):
    repo, usuarios, email = escenario
    viejas = AHORA - timedelta(minutes=11)
    for _ in range(5):
        repo.crear_validacion("u-1", "x" * 64, viejas + timedelta(minutes=10), viejas)
    _solicitar(repo, usuarios, email).ejecutar("u-1", PASSWORD_ACTUAL, None, None)
    assert len(email.codigos) == 1


def test_nueva_solicitud_invalida_la_anterior(escenario):
    repo, usuarios, email = escenario
    _solicitar(repo, usuarios, email, codigo="1111").ejecutar("u-1", PASSWORD_ACTUAL, None, None)
    _solicitar(repo, usuarios, email, codigo="2222").ejecutar("u-1", PASSWORD_ACTUAL, None, None)
    assert repo.validaciones[0].consumido_en is not None
    assert repo.validaciones[1].consumido_en is None


def test_fallo_de_email_no_se_reporta_como_exito(escenario):
    repo, usuarios, _ = escenario
    email = EmailFake(ok=False)
    with pytest.raises(NoSePudoEnviarCodigoError):
        _solicitar(repo, usuarios, email).ejecutar("u-1", PASSWORD_ACTUAL, None, None)


# --- Confirmar cambio ---


def _solicitar_codigo(repo, usuarios, email, codigo="4273"):
    _solicitar(repo, usuarios, email, codigo=codigo).ejecutar("u-1", PASSWORD_ACTUAL, None, None)


def test_confirmar_cambia_hash_consume_codigo_revoca_sesiones_y_audita(escenario):
    repo, usuarios, email = escenario
    _solicitar_codigo(repo, usuarios, email)

    _confirmar(repo, usuarios, email).ejecutar("u-1", "4273", PASSWORD_NUEVA, "10.0.0.2", "ua")

    usuario = usuarios.usuario
    assert HashContrasenaService.verificar(PASSWORD_NUEVA, usuario.hash_contrasena)
    assert usuario.sesiones_revocadas_antes_de == AHORA
    assert repo.validaciones[0].consumido_en == AHORA
    estados = [e for e, _ in repo.auditoria]
    assert "codigo_validado" in estados and "cambio_exitoso" in estados
    assert email.confirmaciones == [("operador@example.com", AHORA, "10.0.0.2")]


def test_codigo_no_se_reutiliza_tras_el_cambio(escenario):
    repo, usuarios, email = escenario
    _solicitar_codigo(repo, usuarios, email)
    _confirmar(repo, usuarios, email).ejecutar("u-1", "4273", PASSWORD_NUEVA, None, None)
    with pytest.raises(CodigoCambioInvalidoError):
        _confirmar(repo, usuarios, email).ejecutar("u-1", "4273", "OtraPass33", None, None)


def test_codigo_expirado_da_400(escenario):
    repo, usuarios, email = escenario
    _solicitar_codigo(repo, usuarios, email)
    despues_del_ttl = AHORA + timedelta(minutes=11)
    with pytest.raises(CodigoCambioInvalidoError):
        _confirmar(repo, usuarios, email, ahora=despues_del_ttl).ejecutar("u-1", "4273", PASSWORD_NUEVA, None, None)


def test_codigo_erroneo_cuenta_intento_y_da_400(escenario):
    repo, usuarios, email = escenario
    _solicitar_codigo(repo, usuarios, email)
    with pytest.raises(CodigoCambioInvalidoError):
        _confirmar(repo, usuarios, email).ejecutar("u-1", "0000", PASSWORD_NUEVA, "10.0.0.3", None)
    assert repo.validaciones[0].intentos_fallidos == 1
    assert repo.validaciones[0].consumido_en is None
    assert ("intento_fallido", "10.0.0.3") in repo.auditoria


def test_quinto_intento_fallido_invalida_el_codigo_y_audita_bloqueo(escenario):
    repo, usuarios, email = escenario
    _solicitar_codigo(repo, usuarios, email)
    for _ in range(5):
        with pytest.raises(CodigoCambioInvalidoError):
            _confirmar(repo, usuarios, email).ejecutar("u-1", "0000", PASSWORD_NUEVA, None, None)
    assert repo.validaciones[0].consumido_en is not None
    assert ("bloqueo_por_intentos", None) in repo.auditoria
    # Aunque ahora llegue el código correcto, ya no sirve.
    with pytest.raises(CodigoCambioInvalidoError):
        _confirmar(repo, usuarios, email).ejecutar("u-1", "4273", PASSWORD_NUEVA, None, None)


def test_contrasena_nueva_debil_da_400_y_no_consume_codigo(escenario):
    repo, usuarios, email = escenario
    _solicitar_codigo(repo, usuarios, email)
    with pytest.raises(ContrasenaDebilError):
        _confirmar(repo, usuarios, email).ejecutar("u-1", "4273", "sinmayus1", None, None)
    assert repo.validaciones[0].consumido_en is None
    assert HashContrasenaService.verificar(PASSWORD_ACTUAL, usuarios.usuario.hash_contrasena)


def test_contrasena_nueva_igual_a_la_actual_da_400(escenario):
    repo, usuarios, email = escenario
    _solicitar_codigo(repo, usuarios, email)
    with pytest.raises(ContrasenaDebilError, match="igual a la actual"):
        _confirmar(repo, usuarios, email).ejecutar("u-1", "4273", PASSWORD_ACTUAL, None, None)
    assert repo.validaciones[0].consumido_en is None


def test_fallo_de_email_de_confirmacion_no_revierte_el_cambio(escenario):
    repo, usuarios, email_ok = escenario
    _solicitar_codigo(repo, usuarios, email_ok)
    email_caido = EmailFake(ok=False)
    _confirmar(repo, usuarios, email_caido).ejecutar("u-1", "4273", PASSWORD_NUEVA, None, None)
    assert HashContrasenaService.verificar(PASSWORD_NUEVA, usuarios.usuario.hash_contrasena)


# --- Límite de solicitudes incluye contraseñas erróneas (adivinación de password_actual) ---


def test_cinco_contrasenas_erroneas_bloquean_la_sexta_aunque_sea_la_correcta(escenario):
    repo, usuarios, email = escenario
    caso = _solicitar(repo, usuarios, email)
    for _ in range(5):
        with pytest.raises(CredencialesInvalidasError):
            caso.ejecutar("u-1", "Incorrecta1", None, None)
    with pytest.raises(DemasiadosIntentosError):
        caso.ejecutar("u-1", PASSWORD_ACTUAL, None, None)
    assert email.codigos == []


def test_exito_no_resetea_el_limite_dentro_de_la_ventana(escenario):
    repo, usuarios, email = escenario
    caso = _solicitar(repo, usuarios, email)
    for _ in range(3):
        with pytest.raises(CredencialesInvalidasError):
            caso.ejecutar("u-1", "Incorrecta1", None, None)
    caso.ejecutar("u-1", PASSWORD_ACTUAL, None, None)  # éxito: 1 solicitud
    with pytest.raises(CredencialesInvalidasError):
        caso.ejecutar("u-1", "Incorrecta1", None, None)  # 5 cuentan en total
    with pytest.raises(DemasiadosIntentosError):
        caso.ejecutar("u-1", PASSWORD_ACTUAL, None, None)


def test_contrasenas_erroneas_viejas_no_cuentan_fuera_de_la_ventana(escenario):
    repo, usuarios, email = escenario
    viejo = AHORA - timedelta(minutes=11)
    for _ in range(5):
        repo.registrar_auditoria("u-1", "intento_fallido", None, None, viejo)
    _solicitar(repo, usuarios, email).ejecutar("u-1", PASSWORD_ACTUAL, None, None)
    assert len(email.codigos) == 1
