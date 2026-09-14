"""src/domain/billing/exceptions.py."""


class DominioBillingException(Exception):
    def __init__(self, mensaje: str):
        super().__init__(mensaje)
        self.mensaje = mensaje


class PayerEmailFaltanteError(DominioBillingException):
    """Lanzada al generar un checkout para una organización sin email_contacto configurado."""
