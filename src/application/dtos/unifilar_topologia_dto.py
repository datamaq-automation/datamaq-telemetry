from pydantic import BaseModel, Field


class SeccionadorDTO(BaseModel):
    id: str
    estado: str = "cerrado"


class InterruptorGeneralMTDTO(BaseModel):
    id: str
    modelo: str
    protecciones: list[str] = Field(default_factory=list)


class AcometidaDTO(BaseModel):
    tension_kv: float
    frecuencia_hz: float = 50
    seccionador: SeccionadorDTO
    interruptor_general_mt: InterruptorGeneralMTDTO


class TransformadorDTO(BaseModel):
    id: str
    potencia_kva: float
    relacion: str
    grupo_conexion: str
    tension_cortocircuito_porc: float
    regimen_neutro: str


class BarraPrincipalDTO(BaseModel):
    id: str
    tension_v: float
    corriente_nominal_a: float
    icw_ka: float
    ipk_ka: float
    conductores: str


class TableroDestinoDTO(BaseModel):
    id: str
    nombre: str


class AlimentadorDTO(BaseModel):
    id: str
    nombre: str
    tipo: str
    corriente_nominal_a: float
    poder_corte_ka: float
    device_uid: str
    tablero_destino: TableroDestinoDTO
    cable: str


class BancoCapacitoresDTO(BaseModel):
    id: str
    potencia_kvar: float
    tipo: str
    reactancia_porc: float
    interruptor_asociado: str


class UnifilarTopologiaDTO(BaseModel):
    acometida: AcometidaDTO
    transformador: TransformadorDTO
    barra_principal: BarraPrincipalDTO
    alimentadores: list[AlimentadorDTO] = Field(default_factory=list)
    banco_capacitores: BancoCapacitoresDTO | None = None
