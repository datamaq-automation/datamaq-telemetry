# Cómo contribuir — datamaq-telemetry

Backend de telemetría (FastAPI y worker MQTT). Arquitectura y comandos: [`AGENTS.md`](AGENTS.md).

- **Reglas de flujo** (Issues, ramas, PRs, commits, comentarios, cierres y confirmaciones): [`../CONTRIBUTING.md`](../CONTRIBUTING.md), del repo padre `datamaq`. Aquí no se repiten.
- **Gauntlet local:** `scripts/pre-push.sh`, siete etapas (0 a 6) que incluyen los tests de integración. Debe quedar verde antes de cerrar un cambio.
- **Reglas propias del código:** imports absolutos `from src....`; los `__init__.py` de 0 bytes; dominio solo con stdlib (`scripts/verify_architecture.py`); límites de tamaño por archivo, clase y método (`scripts/verify_code_size.py`).
- **Tipos y estilo:** `ruff` y `pyright`. Los tests están excluidos de pyright por diseño.
