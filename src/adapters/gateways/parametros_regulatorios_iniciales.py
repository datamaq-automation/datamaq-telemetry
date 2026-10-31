"""src/adapters/gateways/parametros_regulatorios_iniciales.py.

Carga inicial de tarifas, facturas verificadas y parámetros regulatorios (datamaq#111, fase 1).

Son exactamente los valores que vivían como literales en `src/domain` hasta #111, sin cambio de valor. Los
usan la migración Alembic (carga inicial de la base) y el repositorio en memoria de los tests. Los valores van
como texto para conservar la precisión decimal exacta del literal original.
"""

from typing import Any, Final

TARIFAS_CAPACIDAD_INICIALES: Final[tuple[dict[str, Any], ...]] = (
    {
        "distribuidora": "Edesur",
        "tarifa": "T3 MT",
        "periodo": "2025-07",
        "fuente_archivo": "Cristal Avellaneda - EDESUR/2025-07.pdf",
        "vigencia_desde": "2025-07-01",
        "importe_capacidad_convenida_ars": "3521212.94",
        "csc_kw": "848.40",
        "fuente_metodo": "Factura Edesur 2025-07 (LSP A 9904-02469153 17), renglón 'Cap.Sum.Conv T3'. Carga inicial de #111 (literal previo en tarifas_distribuidora.py).",
    },
)

FACTURAS_VERIFICADAS_INICIALES: Final[tuple[dict[str, Any], ...]] = (
    {
        "planta_id": "c64fd625-0037-4caa-b68a-800e8e0ee548",
        "distribuidora": "Edesur",
        "tarifa": "T3 MT",
        "periodo": "2025-07",
        "fuente_archivo": "Cristal Avellaneda - EDESUR/2025-07.pdf",
        "adquirida_kw": "930.00",
        "tg_fi_bloque_punta": None,
        "tg_fi_bloque_valle": None,
        "tg_fi_bloque_resto": None,
        "fuente_metodo": "Durax / Cristal Avellaneda, demanda adquirida de la factura verificada contra el PDF. Carga inicial de #111 (literal previo en penalizacion_periodo.py).",
    },
    {
        "planta_id": "4f68f653-a604-4834-8154-31f938248572",
        "distribuidora": "EDELAP",
        "tarifa": "T5M12",
        "periodo": "2024-08",
        "fuente_archivo": "Papelera platense - EDELAP/2024-08.pdf",
        "adquirida_kw": None,
        "tg_fi_bloque_punta": "0.431",
        "tg_fi_bloque_valle": "0.438",
        "tg_fi_bloque_resto": "0.426",
        "fuente_metodo": "UPP / Papelera platense, tg phi de la factura y Tg. Fi. punta/valle/resto verificados contra el PDF. Carga inicial de #111 (literal previo).",
    },
    {
        "planta_id": "4f68f653-a604-4834-8154-31f938248572",
        "distribuidora": "EDELAP",
        "tarifa": "T5M12",
        "periodo": "2023-12",
        "fuente_archivo": "Papelera platense - EDELAP/2023-12.pdf",
        "adquirida_kw": None,
        "tg_fi_bloque_punta": "0.483",
        "tg_fi_bloque_valle": "0.492",
        "tg_fi_bloque_resto": "0.481",
        "fuente_metodo": "UPP / Papelera platense, tg phi de la factura y Tg. Fi. punta/valle/resto verificados contra el PDF. Carga inicial de #111 (literal previo).",
    },
)

PARAMETROS_REGULATORIOS_INICIALES: Final[tuple[dict[str, Any], ...]] = (
    {
        "clave": "factor_recargo_exceso",
        "valor": "1.5",
        "distribuidora": "Edesur",
        "tarifa": "T3 MT",
        "vigencia_desde": None,
        "fuente_archivo": "Cristal Avellaneda - EDESUR/2025-07.pdf",
        "fuente_metodo": "transcripcion_verificada",
    },
    {
        "clave": "limite_tg_fi_regimen_1992",
        "valor": "0.62",
        "distribuidora": "EDELAP",
        "tarifa": "T5M12",
        "vigencia_desde": None,
        "fuente_archivo": "decisions/2026-10-14_regimen-reactiva-edelap.md",
        "fuente_metodo": "transcripcion_verificada",
    },
)
