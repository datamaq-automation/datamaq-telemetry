from src.application.dtos.unifilar_topologia_dto import (
    AcometidaDTO,
    AlimentadorDTO,
    BancoCapacitoresDTO,
    BarraPrincipalDTO,
    InterruptorGeneralMTDTO,
    SeccionadorDTO,
    TableroDestinoDTO,
    TransformadorDTO,
    UnifilarTopologiaDTO,
)
from src.domain.telemetria.exceptions import PlantaNoEncontradaError
from src.domain.telemetria.ports import RepositorioOrganizacionesPort


class ConsultarUnifilarTopologiaUseCase:
    def __init__(self, repo_organizaciones: RepositorioOrganizacionesPort):
        self.repo_organizaciones = repo_organizaciones

    def ejecutar(self, planta_id: str) -> UnifilarTopologiaDTO:
        planta = self.repo_organizaciones.obtener_planta_por_id(planta_id)
        if not planta:
            raise PlantaNoEncontradaError(f"Planta con id '{planta_id}' no encontrada.")

        # Construir topología desde nodos (mapeo simplificado)
        # En producción, esto vendría de una tabla dedicada o se derivaría de los nodos
        return UnifilarTopologiaDTO(
            acometida=AcometidaDTO(
                tension_kv=13.2,
                frecuencia_hz=50,
                seccionador=SeccionadorDTO(id="QS1", estado="cerrado"),
                interruptor_general_mt=InterruptorGeneralMTDTO(
                    id="QF1", modelo="HVX-12", protecciones=["50/51"]
                ),
            ),
            transformador=TransformadorDTO(
                id="T1",
                potencia_kva=1000,
                relacion="13.2/0.4",
                grupo_conexion="Dyn11",
                tension_cortocircuito_porc=4,
                regimen_neutro="TN-S",
            ),
            barra_principal=BarraPrincipalDTO(
                id="BT-TGBT",
                tension_v=380,
                corriente_nominal_a=1600,
                icw_ka=50,
                ipk_ka=105,
                conductores="3x(1x240)+1x120 mm² Cu XLPE",
            ),
            alimentadores=[
                AlimentadorDTO(
                    id="Q1",
                    nombre="Alimentador Producción",
                    tipo="MCCB",
                    corriente_nominal_a=400,
                    poder_corte_ka=25,
                    device_uid="datamaq-001",
                    tablero_destino=TableroDestinoDTO(id="TS-PROD", nombre="Tablero Seccional Producción"),
                    cable="3x185+1x95 mm² Cu XLPE",
                )
            ],
            banco_capacitores=BancoCapacitoresDTO(
                id="CAP1",
                potencia_kvar=150,
                tipo="Detuned",
                reactancia_porc=5.67,
                interruptor_asociado="Q_CAP",
            ),
        )
