"""src/domain/maquinas/servicios/presets_industriales.py — Catálogo de maquinaria y cargas industriales normalizadas."""

from src.domain.maquinas.entities import Máquina
from src.domain.maquinas.servicios.modelo_motor_industrial import ModeloMotorFisicoService
from src.domain.maquinas.value_objects import (
    CategoriaCarga,
    FirmaCarga,
    NaturalezaElectrica,
    OrigenFirma,
    PatronOperacion,
)


class CatalogoPresetsIndustriales:
    """Genera instancias de Máquina para maquinaria industrial a partir de potencias de chapa estándar."""

    @classmethod
    def crear_motor_trifasico_5_5kw(cls, dispositivo_id: str, maquina_id: str = "motor-5-5kw") -> Máquina:
        p_nom = 5500.0
        firma = ModeloMotorFisicoService.generar_firma_desde_chapa(
            p_nom, factor_carga_esperado=0.75, cos_phi_esperado=0.82
        )
        return Máquina(
            id=maquina_id,
            dispositivo_id=dispositivo_id,
            nombre="Motor Trifásico 5.5 kW (7.5 HP)",
            categoria=CategoriaCarga.FUERZA_MOTRIZ,
            naturaleza_electrica=NaturalezaElectrica.MOTOR,
            patron_operacion=PatronOperacion.CONTINUO_DIARIO,
            potencia_nominal_w=p_nom,
            firma=firma,
        )

    @classmethod
    def crear_motor_trifasico_11kw(cls, dispositivo_id: str, maquina_id: str = "motor-11kw") -> Máquina:
        p_nom = 11000.0
        firma = ModeloMotorFisicoService.generar_firma_desde_chapa(
            p_nom, factor_carga_esperado=0.75, cos_phi_esperado=0.84
        )
        return Máquina(
            id=maquina_id,
            dispositivo_id=dispositivo_id,
            nombre="Motor Trifásico 11 kW (15 HP)",
            categoria=CategoriaCarga.FUERZA_MOTRIZ,
            naturaleza_electrica=NaturalezaElectrica.MOTOR,
            patron_operacion=PatronOperacion.CONTINUO_DIARIO,
            potencia_nominal_w=p_nom,
            firma=firma,
        )

    @classmethod
    def crear_motor_trifasico_22kw(cls, dispositivo_id: str, maquina_id: str = "motor-22kw") -> Máquina:
        p_nom = 22000.0
        firma = ModeloMotorFisicoService.generar_firma_desde_chapa(
            p_nom, factor_carga_esperado=0.75, cos_phi_esperado=0.86
        )
        return Máquina(
            id=maquina_id,
            dispositivo_id=dispositivo_id,
            nombre="Motor Trifásico 22 kW (30 HP)",
            categoria=CategoriaCarga.FUERZA_MOTRIZ,
            naturaleza_electrica=NaturalezaElectrica.MOTOR,
            patron_operacion=PatronOperacion.CONTINUO_DIARIO,
            potencia_nominal_w=p_nom,
            firma=firma,
        )

    @classmethod
    def crear_motor_trifasico_45kw(cls, dispositivo_id: str, maquina_id: str = "motor-45kw") -> Máquina:
        p_nom = 45000.0
        firma = ModeloMotorFisicoService.generar_firma_desde_chapa(
            p_nom, factor_carga_esperado=0.80, cos_phi_esperado=0.88
        )
        return Máquina(
            id=maquina_id,
            dispositivo_id=dispositivo_id,
            nombre="Motor Trifásico 45 kW (60 HP)",
            categoria=CategoriaCarga.FUERZA_MOTRIZ,
            naturaleza_electrica=NaturalezaElectrica.MOTOR,
            patron_operacion=PatronOperacion.CONTINUO_DIARIO,
            potencia_nominal_w=p_nom,
            firma=firma,
        )

    @classmethod
    def crear_compresor_tornillo_37kw(cls, dispositivo_id: str, maquina_id: str = "compresor-37kw") -> Máquina:
        p_nom = 37000.0
        firma = ModeloMotorFisicoService.generar_firma_desde_chapa(
            p_nom, factor_carga_esperado=0.85, cos_phi_esperado=0.87
        )
        return Máquina(
            id=maquina_id,
            dispositivo_id=dispositivo_id,
            nombre="Compresor de Tornillo 37 kW (50 HP)",
            categoria=CategoriaCarga.FUERZA_MOTRIZ,
            naturaleza_electrica=NaturalezaElectrica.MOTOR,
            patron_operacion=PatronOperacion.CICLICO_TERMOSTATICO,
            potencia_nominal_w=p_nom,
            firma=firma,
        )

    @classmethod
    def crear_horno_resistivo_50kw(cls, dispositivo_id: str, maquina_id: str = "horno-50kw") -> Máquina:
        p_nom = 50000.0
        return Máquina(
            id=maquina_id,
            dispositivo_id=dispositivo_id,
            nombre="Horno Industrial Resistivo 50 kW",
            categoria=CategoriaCarga.OTROS,
            naturaleza_electrica=NaturalezaElectrica.RESISTIVA,
            patron_operacion=PatronOperacion.MANUAL_PROLONGADO,
            potencia_nominal_w=p_nom,
            firma=FirmaCarga(
                potencia_w=p_nom,
                dispersion_w=1000.0,
                potencia_reactiva_var=0.0,
                factor_potencia=1.0,
                origen=OrigenFirma.CHAPA,
            ),
        )
