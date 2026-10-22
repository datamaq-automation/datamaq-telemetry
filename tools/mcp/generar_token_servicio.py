#!/usr/bin/env python3
"""tools/mcp/generar_token_servicio.py — Generador de tokens JWT de servicio / larga duración.

Permite generar tokens JWT autónomos para el servidor FastMCP (o integraciones de servicio)
usando la clave secreta institucional configurada en Settings().API_SECRET_KEY.
"""

import argparse
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Permitir ejecución directa del script sin necesidad de configurar PYTHONPATH manualmente
_repo_root = Path(__file__).resolve().parent.parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from src.infrastructure.auth.jwt_token_service import JwtTokenService  # noqa: E402
from src.infrastructure.settings.config import get_settings  # noqa: E402


def generar_token_servicio(
    dias: int = 365,
    usuario: str = "mcp_service",
    rol: str = "superadmin",
    organizacion_id: str | None = None,
    usuario_id: str | None = None,
    secret_key: str | None = None,
) -> str:
    """Genera un token JWT firmado de servicio con la duración y rol especificados.

    Args:
        dias: Cantidad de días de validez del token (por defecto 365).
        usuario: Nombre o identificador lógico de la cuenta de servicio.
        rol: Rol asignado al token ('superadmin', 'administrador', 'operador').
        organizacion_id: Identificador de organización opcional.
        usuario_id: UUID o ID del sujeto ('sub'). Si es None, se genera un UUIDv4.
        secret_key: Clave secreta HMAC. Si es None, se obtiene de get_settings().API_SECRET_KEY.

    Returns:
        Token JWT firmado en formato string.
    """
    if dias <= 0:
        raise ValueError("El parámetro dias debe ser un entero positivo mayor a 0.")

    clave = secret_key if secret_key is not None else get_settings().API_SECRET_KEY
    if not clave:
        raise ValueError("No se pudo obtener una clave secreta válida desde get_settings().API_SECRET_KEY.")

    sub = usuario_id if usuario_id is not None else str(uuid.uuid4())
    ahora = datetime.now(timezone.utc)
    expira_en = ahora + timedelta(days=dias)

    token_service = JwtTokenService(clave)
    return token_service.generar(
        usuario_id=sub,
        usuario=usuario,
        expira_en=expira_en,
        rol=rol,
        organizacion_id=organizacion_id,
    )


def construir_instrucciones(token: str, usuario: str, rol: str, dias: int) -> str:
    """Genera el texto de instrucciones para configurar el token en .env y claude_desktop_config.json."""
    return f"""================================================================================
TOKEN JWT DE SERVICIO GENERADO EXITOSAMENTE
================================================================================
Usuario:  {usuario}
Rol:      {rol}
Validez:  {dias} días

Token JWT:
{token}

--------------------------------------------------------------------------------
1. Para configurar en archivo .env (VPS o entorno local):
--------------------------------------------------------------------------------
DATAMAQ_AUTH_TOKEN={token}

--------------------------------------------------------------------------------
2. Para configurar en Claude Desktop (claude_desktop_config.json):
--------------------------------------------------------------------------------
{{
  "mcpServers": {{
    "datamaq": {{
      "command": "python",
      "args": ["-m", "tools.mcp.server"],
      "env": {{
        "DATAMAQ_API_URL": "https://api.datamaq.com.ar",
        "DATAMAQ_AUTH_TOKEN": "{token}"
      }}
    }}
  }}
}}
================================================================================"""


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada CLI para la generación de tokens de servicio."""
    parser = argparse.ArgumentParser(
        description="Genera tokens JWT de servicio institucional / larga duración para DataMaq FastMCP.",
    )
    parser.add_argument(
        "--dias",
        type=int,
        default=365,
        help="Días de validez del token JWT (por defecto: 365 días).",
    )
    parser.add_argument(
        "--usuario",
        type=str,
        default="mcp_service",
        help="Identificador del usuario / servicio (por defecto: mcp_service).",
    )
    parser.add_argument(
        "--rol",
        type=str,
        default="superadmin",
        help="Rol asignado al token (por defecto: superadmin).",
    )
    parser.add_argument(
        "--org",
        type=str,
        default=None,
        help="Identificador opcional de organización.",
    )
    parser.add_argument(
        "--solo-token",
        action="store_true",
        help="Imprime únicamente el token JWT plano en stdout (útil para pipes/scripts).",
    )

    args = parser.parse_args(argv)

    try:
        token = generar_token_servicio(
            dias=args.dias,
            usuario=args.usuario,
            rol=args.rol,
            organizacion_id=args.org,
        )
    except Exception as exc:
        sys.stderr.write(f"Error generando token de servicio: {exc}\n")
        return 1

    if args.solo_token:
        sys.stdout.write(token + "\n")
    else:
        sys.stdout.write(construir_instrucciones(token, args.usuario, args.rol, args.dias) + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
