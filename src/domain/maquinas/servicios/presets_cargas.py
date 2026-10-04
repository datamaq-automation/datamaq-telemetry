"""src/domain/maquinas/servicios/presets_cargas.py — Catálogo de presets de cargas típicas y firmas estándar de fábrica."""

from src.domain.maquinas.entities import Máquina
from src.domain.maquinas.value_objects import (
    CategoriaCarga,
    FirmaCarga,
    NaturalezaElectrica,
    OrigenFirma,
    PatronOperacion,
)


class CatalogoPresetsCargas:
    """Genera instancias de Máquina con firmas precalibradas según física típica."""

    @classmethod
    def crear_heladera(cls, dispositivo_id: str, maquina_id: str = "carga-heladera") -> Máquina:
        return Máquina(
            id=maquina_id,
            dispositivo_id=dispositivo_id,
            nombre="Heladera",
            categoria=CategoriaCarga.REFRIGERACION,
            naturaleza_electrica=NaturalezaElectrica.MOTOR,
            patron_operacion=PatronOperacion.CICLICO_TERMOSTATICO,
            potencia_nominal_w=120.0,
            firma=FirmaCarga(
                potencia_w=120.0,
                dispersion_w=12.0,
                potencia_reactiva_var=95.0,
                factor_potencia=0.72,
                duracion_encendido_s=1500.0,  # 25 min
                duracion_apagado_s=1800.0,  # 30 min
                origen=OrigenFirma.CHAPA,
            ),
        )

    @classmethod
    def crear_freezer(cls, dispositivo_id: str, maquina_id: str = "carga-freezer") -> Máquina:
        return Máquina(
            id=maquina_id,
            dispositivo_id=dispositivo_id,
            nombre="Freezer",
            categoria=CategoriaCarga.REFRIGERACION,
            naturaleza_electrica=NaturalezaElectrica.MOTOR,
            patron_operacion=PatronOperacion.CICLICO_TERMOSTATICO,
            potencia_nominal_w=180.0,
            firma=FirmaCarga(
                potencia_w=180.0,
                dispersion_w=15.0,
                potencia_reactiva_var=135.0,
                factor_potencia=0.68,
                duracion_encendido_s=2100.0,  # 35 min
                duracion_apagado_s=2400.0,  # 40 min
                origen=OrigenFirma.CHAPA,
            ),
        )

    @classmethod
    def crear_pava_electrica(cls, dispositivo_id: str, maquina_id: str = "carga-pava") -> Máquina:
        return Máquina(
            id=maquina_id,
            dispositivo_id=dispositivo_id,
            nombre="Pava eléctrica",
            categoria=CategoriaCarga.COCCION,
            naturaleza_electrica=NaturalezaElectrica.RESISTIVA,
            patron_operacion=PatronOperacion.MANUAL_PULSO,
            potencia_nominal_w=1850.0,
            firma=FirmaCarga(
                potencia_w=1850.0,
                dispersion_w=25.0,
                potencia_reactiva_var=8.0,
                factor_potencia=0.99,
                duracion_encendido_s=180.0,  # 3 min
                origen=OrigenFirma.CHAPA,
            ),
        )

    @classmethod
    def crear_termotanque(cls, dispositivo_id: str, maquina_id: str = "carga-termotanque") -> Máquina:
        return Máquina(
            id=maquina_id,
            dispositivo_id=dispositivo_id,
            nombre="Termotanque eléctrico",
            categoria=CategoriaCarga.CALENTAMIENTO_AGUA,
            naturaleza_electrica=NaturalezaElectrica.RESISTIVA,
            patron_operacion=PatronOperacion.CICLICO_TERMOSTATICO,
            potencia_nominal_w=1800.0,
            firma=FirmaCarga(
                potencia_w=1800.0,
                dispersion_w=30.0,
                potencia_reactiva_var=12.0,
                factor_potencia=0.99,
                duracion_encendido_s=2700.0,  # 45 min
                origen=OrigenFirma.CHAPA,
            ),
        )

    @classmethod
    def crear_anafe_electrico(cls, dispositivo_id: str, maquina_id: str = "carga-anafe") -> Máquina:
        return Máquina(
            id=maquina_id,
            dispositivo_id=dispositivo_id,
            nombre="Anafe eléctrico",
            categoria=CategoriaCarga.COCCION,
            naturaleza_electrica=NaturalezaElectrica.RESISTIVA,
            patron_operacion=PatronOperacion.MANUAL_PROLONGADO,
            potencia_nominal_w=1500.0,
            firma=FirmaCarga(
                potencia_w=1500.0,
                dispersion_w=35.0,
                potencia_reactiva_var=10.0,
                factor_potencia=0.99,
                duracion_encendido_s=900.0,  # 15 min
                origen=OrigenFirma.CHAPA,
            ),
        )

    @classmethod
    def crear_horno_electrico(cls, dispositivo_id: str, maquina_id: str = "carga-horno") -> Máquina:
        return Máquina(
            id=maquina_id,
            dispositivo_id=dispositivo_id,
            nombre="Horno eléctrico",
            categoria=CategoriaCarga.COCCION,
            naturaleza_electrica=NaturalezaElectrica.RESISTIVA,
            patron_operacion=PatronOperacion.MANUAL_PROLONGADO,
            potencia_nominal_w=2200.0,
            firma=FirmaCarga(
                potencia_w=2200.0,
                dispersion_w=40.0,
                potencia_reactiva_var=15.0,
                factor_potencia=0.99,
                duracion_encendido_s=4500.0,  # 75 min
                origen=OrigenFirma.CHAPA,
            ),
        )

    @classmethod
    def crear_caloventor(cls, dispositivo_id: str, maquina_id: str = "carga-caloventor") -> Máquina:
        return Máquina(
            id=maquina_id,
            dispositivo_id=dispositivo_id,
            nombre="Caloventor",
            categoria=CategoriaCarga.CLIMATIZACION,
            naturaleza_electrica=NaturalezaElectrica.MIXTA,
            patron_operacion=PatronOperacion.MANUAL_PROLONGADO,
            potencia_nominal_w=2000.0,
            firma=FirmaCarga(
                potencia_w=2000.0,
                dispersion_w=30.0,
                potencia_reactiva_var=35.0,
                factor_potencia=0.98,
                duracion_encendido_s=3600.0,  # 60 min
                origen=OrigenFirma.CHAPA,
            ),
        )

    @classmethod
    def crear_pc_escritorio(cls, dispositivo_id: str, maquina_id: str = "carga-pc") -> Máquina:
        return Máquina(
            id=maquina_id,
            dispositivo_id=dispositivo_id,
            nombre="Computadora / PC",
            categoria=CategoriaCarga.OTROS,
            naturaleza_electrica=NaturalezaElectrica.ELECTRONICA,
            patron_operacion=PatronOperacion.MANUAL_PROLONGADO,
            potencia_nominal_w=180.0,
            firma=FirmaCarga(
                potencia_w=180.0,
                dispersion_w=25.0,
                potencia_reactiva_var=45.0,
                factor_potencia=0.92,
                duracion_encendido_s=7200.0,  # 120 min
                origen=OrigenFirma.CHAPA,
            ),
        )

    @classmethod
    def crear_iluminacion(cls, dispositivo_id: str, maquina_id: str = "carga-iluminacion") -> Máquina:
        return Máquina(
            id=maquina_id,
            dispositivo_id=dispositivo_id,
            nombre="Iluminación",
            categoria=CategoriaCarga.ILUMINACION,
            naturaleza_electrica=NaturalezaElectrica.ELECTRONICA,
            patron_operacion=PatronOperacion.CONTINUO_DIARIO,
            potencia_nominal_w=65.0,
            firma=FirmaCarga(
                potencia_w=65.0,
                dispersion_w=5.0,
                potencia_reactiva_var=20.0,
                factor_potencia=0.80,
                duracion_encendido_s=10800.0,  # 180 min
                origen=OrigenFirma.CHAPA,
            ),
        )

    @classmethod
    def obtener_todas(cls, dispositivo_id: str) -> list[Máquina]:
        return [
            cls.crear_heladera(dispositivo_id),
            cls.crear_freezer(dispositivo_id),
            cls.crear_pava_electrica(dispositivo_id),
            cls.crear_termotanque(dispositivo_id),
            cls.crear_anafe_electrico(dispositivo_id),
            cls.crear_horno_electrico(dispositivo_id),
            cls.crear_caloventor(dispositivo_id),
            cls.crear_pc_escritorio(dispositivo_id),
            cls.crear_iluminacion(dispositivo_id),
        ]
