"""tests/unit/test_monitor_potencia_tuya.py."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.use_cases.monitorear_potencia_y_alarma import MonitorearPotenciaYAlarmaUseCase
from src.domain.notificaciones.servicios.monitor_potencia_tuya import MonitorPotenciaTuyaService
from src.domain.telemetria.exceptions import PlantaNoEncontradaError


class TestMonitorPotenciaTuyaService:
    """Tests del servicio de evaluación de alarma con histéresis."""

    def test_histéresis_90_85_por_debajo_umbral(self):
        """Al 85%, sin alarma previa -> no activa."""
        servicio = MonitorPotenciaTuyaService()
        resultado = servicio.evaluar_alarma(
            potencia_adquirida_w=8500.0,
            potencia_contratada_w=10000.0,
            alarma_sonora_activa=False,
        )
        assert resultado["alarma_activar"] is False
        assert resultado["porcentaje_uso"] == 85.0

    def test_histéresis_90_85_por_encima_umbral(self):
        """Al 90%, sin alarma previa -> activa."""
        servicio = MonitorPotenciaTuyaService()
        resultado = servicio.evaluar_alarma(
            potencia_adquirida_w=9000.0,
            potencia_contratada_w=10000.0,
            alarma_sonora_activa=False,
        )
        assert resultado["alarma_activar"] is True
        assert resultado["porcentaje_uso"] == 90.0

    def test_histéresis_mantiene_estado_en_zona_muerta(self):
        """Entre 85% y 90% mantiene estado anterior (histéresis)."""
        servicio = MonitorPotenciaTuyaService()

        resultado_activa = servicio.evaluar_alarma(
            potencia_adquirida_w=8800.0,
            potencia_contratada_w=10000.0,
            alarma_sonora_activa=True,
        )
        assert resultado_activa["alarma_activar"] is True

        resultado_inactiva = servicio.evaluar_alarma(
            potencia_adquirida_w=8800.0,
            potencia_contratada_w=10000.0,
            alarma_sonora_activa=False,
        )
        assert resultado_inactiva["alarma_activar"] is False

    def test_potencia_contratada_cero_no_activa_alarma(self):
        """Si potencia contratada es 0, no activa alarma."""
        servicio = MonitorPotenciaTuyaService()
        resultado = servicio.evaluar_alarma(
            potencia_adquirida_w=5000.0,
            potencia_contratada_w=0.0,
            alarma_sonora_activa=False,
        )
        assert resultado["alarma_activar"] is False
        assert resultado["porcentaje_uso"] == 0.0

    def test_retorna_valores_correctos(self):
        """Verifica que se retornan todos los valores esperados."""
        servicio = MonitorPotenciaTuyaService()
        resultado = servicio.evaluar_alarma(
            potencia_adquirida_w=7500.0,
            potencia_contratada_w=10000.0,
            alarma_sonora_activa=False,
        )
        assert resultado["potencia_adquirida_w"] == 7500.0
        assert resultado["potencia_contratada_w"] == 10000.0
        assert resultado["porcentaje_uso"] == 75.0
        assert "alarma_activar" in resultado


class TestMonitorearPotenciaYAlarmaUseCase:
    """Tests del use case de monitoreo."""

    @pytest.mark.asyncio
    async def test_planta_no_encontrada_lanza_error(self):
        """Lanza error si la planta no existe."""
        repo_org = MagicMock()
        repo_org.obtener_planta_por_id.return_value = None
        buffer = MagicMock()
        publisher = MagicMock()

        use_case = MonitorearPotenciaYAlarmaUseCase(repo_org, buffer, publisher)

        with pytest.raises(PlantaNoEncontradaError):
            await use_case.ejecutar("planta_inexistente")

    @pytest.mark.asyncio
    async def test_ejecutar_retorna_dto_correcto(self):
        """Ejecutar retorna DTO con estructura correcta."""
        repo_org = MagicMock()
        planta = MagicMock()
        repo_org.obtener_planta_por_id.return_value = planta
        repo_org.obtener_nodos_unifilar.return_value = []

        factura = MagicMock()
        factura.tipo_dato = "potencia"
        factura.potencia_contratada_punta_kw = 10.0
        factura.potencia_contratada_fuera_punta_kw = None
        repo_org.obtener_facturas_planta.return_value = [factura]

        buffer = MagicMock()
        publisher = AsyncMock()
        publisher.publicar_alarma_sonora.return_value = True

        use_case = MonitorearPotenciaYAlarmaUseCase(repo_org, buffer, publisher)

        resultado = await use_case.ejecutar("planta_test")

        assert resultado.alarma_activa is False
        assert resultado.potencia_contratada_w == 10000.0
        assert resultado.porcentaje_uso == 0.0
        assert resultado.ultimo_evento is not None

    @pytest.mark.asyncio
    async def test_publica_comando_al_cambiar_estado(self):
        """Publica comando MQTT cuando hay cambio de estado de alarma."""
        repo_org = MagicMock()
        planta = MagicMock()
        repo_org.obtener_planta_por_id.return_value = planta
        repo_org.obtener_nodos_unifilar.return_value = []

        factura = MagicMock()
        factura.tipo_dato = "potencia"
        factura.potencia_contratada_punta_kw = 10.0
        factura.potencia_contratada_fuera_punta_kw = None
        repo_org.obtener_facturas_planta.return_value = [factura]

        buffer = MagicMock()
        publisher = AsyncMock()
        publisher.publicar_alarma_sonora.return_value = True

        use_case = MonitorearPotenciaYAlarmaUseCase(repo_org, buffer, publisher)
        use_case._obtener_potencia_adquirida_viva = MagicMock(return_value=9500.0)

        await use_case.ejecutar("planta_test")

        assert publisher.publicar_alarma_sonora.called

    @pytest.mark.asyncio
    async def test_no_publica_si_no_hay_cambio_estado(self):
        """No publica comando si el estado de la alarma no cambia."""
        repo_org = MagicMock()
        planta = MagicMock()
        planta.potencia_contratada_kw = 10.0
        repo_org.obtener_planta_por_id.return_value = planta
        repo_org.obtener_nodos_unifilar.return_value = []

        buffer = MagicMock()
        publisher = AsyncMock()

        use_case = MonitorearPotenciaYAlarmaUseCase(repo_org, buffer, publisher)
        use_case._estado_alarma_anterior = False
        use_case._obtener_potencia_adquirida_viva = MagicMock(return_value=5000.0)

        await use_case.ejecutar("planta_test")

        assert not publisher.publicar_alarma_sonora.called

    def test_obtener_potencia_sin_nodos(self):
        """Retorna None si no hay nodos en la planta."""
        repo_org = MagicMock()
        repo_org.obtener_nodos_unifilar.return_value = []

        buffer = MagicMock()
        publisher = MagicMock()

        use_case = MonitorearPotenciaYAlarmaUseCase(repo_org, buffer, publisher)

        resultado = use_case._obtener_potencia_adquirida_viva("planta_test")

        assert resultado is None


class TestEstadoAlarmaSinEfectos:
    """Issue #98 paso 1: el GET evalúa sin publicar ni instanciar cliente MQTT."""

    @staticmethod
    def _repo_con_potencia_alta() -> MagicMock:
        repo_org = MagicMock()
        repo_org.obtener_planta_por_id.return_value = MagicMock()
        repo_org.obtener_nodos_unifilar.return_value = []
        factura = MagicMock()
        factura.tipo_dato = "potencia"
        factura.potencia_contratada_punta_kw = 10.0
        factura.potencia_contratada_fuera_punta_kw = None
        repo_org.obtener_facturas_planta.return_value = [factura]
        return repo_org

    @pytest.mark.asyncio
    async def test_get_sin_publisher_no_publica_y_devuelve_estado_evaluado(self):
        """Sin publisher, una evaluación que activaría la alarma devuelve alarmaActiva=True y no publica."""
        use_case = MonitorearPotenciaYAlarmaUseCase(self._repo_con_potencia_alta(), MagicMock())
        use_case._obtener_potencia_adquirida_viva = MagicMock(return_value=9500.0)

        resultado = await use_case.ejecutar("planta_test")

        assert resultado.alarma_activa is True
        assert use_case._publisher is None

    def test_dependencia_get_no_instancia_tuya_publisher(self):
        """La DI del GET no construye TuyaPublisher (no crea cliente MQTT)."""
        from unittest.mock import patch

        from src.infrastructure.fastapi import dependencies

        with (
            patch("src.infrastructure.tuya.tuya_publisher.TuyaPublisher") as publisher_cls,
            patch.object(dependencies, "YamlOrganizacionesRepository"),
        ):
            use_case = dependencies.get_monitorear_potencia_use_case(MagicMock())

        publisher_cls.assert_not_called()
        assert use_case._publisher is None
