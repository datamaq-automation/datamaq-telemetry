import io

import pyotp
import qrcode
import qrcode.image.svg

from src.domain.auth.ports import ServicioTOTPPort


class PyOtpService(ServicioTOTPPort):
    def generar_secreto(self) -> str:
        return pyotp.random_base32()

    def verificar_codigo(self, secreto: str, codigo: str) -> bool:
        codigo_limpio = codigo.strip().replace(" ", "").replace("-", "")
        if not codigo_limpio:
            return False
        try:
            totp = pyotp.TOTP(secreto)
            return bool(totp.verify(codigo_limpio, valid_window=1))
        except Exception:
            return False

    def generar_uri(self, usuario: str, secreto: str, emisor: str = "DataMaq") -> str:
        totp = pyotp.TOTP(secreto)
        return totp.provisioning_uri(name=usuario, issuer_name=emisor)

    def generar_qr_svg(self, uri: str) -> str:
        factory = qrcode.image.svg.SvgPathImage
        img = qrcode.make(uri, image_factory=factory)
        stream = io.BytesIO()
        img.save(stream)
        return stream.getvalue().decode("utf-8")
