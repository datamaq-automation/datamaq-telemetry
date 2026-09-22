#!/bin/bash
# Diagnóstico de bug de potencia activa extrema en nodo MT
#
# Verifica las 5 hipótesis del análisis en BD:
#   D1: Duplicados en frontera (mismo device_id dos veces)
#   D2: Nodo MT aparece en su propia frontera (ciclo o bifurcación)
#   D4: Bifurcaciones inesperadas en MT
#
# Uso:
#   ./scripts/diagnose-mt-potencia.sh c64fd625-0037-4caa-b68a-800e8e0ee548 acometida-13200v
#   ./scripts/diagnose-mt-potencia.sh c64fd625-0037-4caa-b68a-800e8e0ee548  # solo estructura
#
# Nota: facility_id es el UUID de la planta, no una cadena como "durax"

set -e

FACILITY_ID="${1:-}"
NODO_ID="${2:-}"

if [ -z "$FACILITY_ID" ]; then
    echo "Uso: $0 <facility-id> [nodo-id]"
    echo ""
    echo "Ejemplos:"
    echo "  $0 c64fd625-0037-4caa-b68a-800e8e0ee548 acometida-13200v"
    echo "  $0 c64fd625-0037-4caa-b68a-800e8e0ee548"
    echo ""
    echo "Para obtener facility_id:"
    echo "  mysql -u datamaq -pdatamaq2026 datamaq_telemetry -e 'SELECT id, name FROM facilities;'"
    exit 1
fi

cd "$(dirname "$0")/.." || exit 1

# Ejecutar script Python con los parámetros
venv/bin/python -m scripts.diagnose_mt_potencia_bug \
    --planta-id "$FACILITY_ID" \
    ${NODO_ID:+--nodo-id "$NODO_ID"}

echo ""
echo "✓ Diagnóstico completado."
echo ""
echo "Si encontraste 'hay_duplicados: true', revisa:"
echo "  - La estructura del árbol unifilar para detectar ciclos"
echo "  - Si el mismo device_id aparece en múltiples nodos"
echo "  - Si hay bifurcaciones anómalas en nodos MT"
