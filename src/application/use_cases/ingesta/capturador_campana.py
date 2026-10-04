"""src/application/use_cases/ingesta/capturador_campana.py — Sumidero paralelo que persiste lecturas a caudal completo durante una campaña."""

from src.application.use_cases.ingesta.registro_campanas import RegistroCampanasActivas
from src.domain.maquinas.ports import RepositorioEnsayosPort
from src.domain.maquinas.value_objects import MuestraCampana
from src.domain.telemetria.entities import LecturaInstantanea
from src.domain.telemetria.ports import LoggerPort


class CapturadorCampanaIngesta:
    """Guarda cada lectura entrante mientras haya una campaña abierta para ese medidor.

    Es un **sumidero paralelo**: no toca el downsampling de 300 s ni escribe en
    `telemetry_instantaneous`. La serie permanente sigue siendo exactamente la misma
    con campaña o sin ella; lo único que cambia es que, durante la ventana, además se
    guarda todo en `campaign_samples`.

    Es la contracara de un hecho ya presente en la plataforma: cuando hay un cliente
    WebSocket conectado, el servidor pone a los medidores en ráfaga cada 60 s y ese
    caudal llega y se descarta. Acá se lo conserva, pero solo durante una ventana
    declarada y con destino acotado.

    Un fallo capturando nunca interrumpe la ingesta: perder una muestra de campaña es
    molesto y se resuelve repitiéndola; perder la telemetría permanente, no.
    """

    def __init__(
        self,
        repo_campanas: RepositorioEnsayosPort,
        registro: RegistroCampanasActivas,
        logger: LoggerPort | None = None,
    ):
        self.repo_campanas = repo_campanas
        self.registro = registro
        self.logger = logger

    @staticmethod
    def _a_muestra(lectura: LecturaInstantanea) -> MuestraCampana | None:
        """Una lectura sin potencia activa no aporta a la firma y no se guarda."""
        if lectura.potencia_activa_total is None:
            return None
        return MuestraCampana(
            momento=lectura.registrado_en,
            potencia_w=float(lectura.potencia_activa_total.vatios),
            potencia_reactiva_var=(
                float(lectura.potencia_reactiva_total.var) if lectura.potencia_reactiva_total else None
            ),
            potencia_aparente_va=(
                float(lectura.potencia_aparente_total.va) if lectura.potencia_aparente_total else None
            ),
            factor_potencia=(float(lectura.factor_potencia_total.valor) if lectura.factor_potencia_total else None),
            tension_v=float(lectura.fase_r.tension.voltios) if lectura.fase_r.tension else None,
            corriente_a=float(lectura.fase_r.corriente.amperios) if lectura.fase_r.corriente else None,
        )

    def capturar(self, dispositivo_id: str, lectura: LecturaInstantanea) -> bool:
        """`True` si la lectura se guardó como muestra de campaña."""
        campana_id = self.registro.campana_de(dispositivo_id, ahora=lectura.registrado_en)
        if campana_id is None:
            return False

        muestra = self._a_muestra(lectura)
        if muestra is None:
            return False

        try:
            return self.repo_campanas.agregar_muestra(campana_id, muestra)
        except Exception as e:
            if self.logger:
                self.logger.warning(
                    "campana_muestra_no_capturada",
                    campana_id=campana_id,
                    dispositivo_id=dispositivo_id,
                    error=str(e),
                )
            return False
