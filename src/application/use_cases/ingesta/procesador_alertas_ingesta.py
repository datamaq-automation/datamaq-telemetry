"""src/application/use_cases/ingesta/procesador_alertas_ingesta.py."""
from datetime import datetime
from typing import ClassVar

from src.application.mappers.alerta_mapper import AlertaMapper
from src.domain.telemetria.entities import (
    AlertaDispositivo,
    Dispositivo,
    LecturaInstantanea,
)
from src.domain.telemetria.ports import (
    LoggerPort,
    NotificadorAlertasPort,
    PublicadorEventosPort,
    RepositorioTelemetriaPort,
)
from src.domain.telemetria.services import (
    AnalizadorCalidadEnergiaService,
    CooldownNotificacionesAlertasService,
    FiltroPersistenciaTemporalService,
)
from src.domain.telemetria.value_objects import SeveridadAlerta


def _notificar_alerta_si_corresponde(
    alerta: AlertaDispositivo,
    dispositivo: Dispositivo | None,
) -> None:
    notif = ProcesadorAlertasIngesta._notificador
    dests = ProcesadorAlertasIngesta._destinatarios
    if alerta.severidad == SeveridadAlerta.CRITICAL and notif is not None and dispositivo is not None and dests:
        cd = ProcesadorAlertasIngesta._cooldown_notificaciones
        if cd.debe_notificar(alerta.dispositivo_id, alerta.tipo_alerta):
            notif.notificar_alerta_critica(alerta, dispositivo, dests)
            cd.registrar_notificacion(alerta.dispositivo_id, alerta.tipo_alerta)


def _despachar_alerta_fn(
    alerta: AlertaDispositivo,
    mac_raw: str,
    repo_telemetria: RepositorioTelemetriaPort,
    publicador: PublicadorEventosPort | None,
    logger: LoggerPort | None,
    dispositivo: Dispositivo | None = None,
) -> None:
    repo_telemetria.guardar_alerta(alerta)
    if publicador:
        publicador.publicar_telemetria_en_vivo(
            f"m/wifi/{mac_raw}/alertas",
            AlertaMapper.to_dto(alerta).model_dump(mode="json"),
        )
    if logger:
        logger.warning(
            "alerta_calidad_energia_detectada",
            dispositivo_id=alerta.dispositivo_id,
            tipo=alerta.tipo_alerta,
            severidad=alerta.severidad.value,
            mensaje=alerta.mensaje,
        )
    _notificar_alerta_si_corresponde(alerta, dispositivo)


def _auto_resolver_alertas_fn(
    dispositivo_id: str,
    mac_raw: str,
    tipos_alerta: list[str],
    recorded_at: datetime,
    repo_telemetria: RepositorioTelemetriaPort,
    publicador: PublicadorEventosPort | None,
    logger: LoggerPort | None,
) -> None:
    alertas_abiertas = repo_telemetria.listar_alertas(
        dispositivo_id=dispositivo_id,
        solo_abiertas=True,
    )
    for a in alertas_abiertas:
        if a.tipo_alerta in tipos_alerta:
            a.marcar_resuelta(
                recorded_at,
                observaciones="Despeje automático: la variable normalizó su valor dentro del rango admisible.",
            )
            repo_telemetria.guardar_alerta(a)
            ProcesadorAlertasIngesta._cooldown_notificaciones.resetear(dispositivo_id, a.tipo_alerta)
            if publicador:
                publicador.publicar_telemetria_en_vivo(
                    f"m/wifi/{mac_raw}/alertas",
                    AlertaMapper.to_dto(a).model_dump(mode="json"),
                )
            if logger:
                logger.info(
                    "alerta_auto_resuelta_normalizada",
                    dispositivo_id=dispositivo_id,
                    tipo=a.tipo_alerta,
                    duracion_segundos=a.duracion_segundos,
                )


class ProcesadorAlertasIngesta:
    """Orquesta la evaluación, persistencia temporal y auto-resolución de alertas normativas."""

    _filtro_persistencia: ClassVar[FiltroPersistenciaTemporalService] = FiltroPersistenciaTemporalService()
    _cooldown_notificaciones: ClassVar[CooldownNotificacionesAlertasService] = CooldownNotificacionesAlertasService()
    _notificador: ClassVar[NotificadorAlertasPort | None] = None
    _destinatarios: ClassVar[list[str]] = []

    @classmethod
    def configurar_notificador(
        cls,
        notificador: NotificadorAlertasPort | None,
        destinatarios: list[str] | None = None,
    ) -> None:
        cls._notificador = notificador
        cls._destinatarios = destinatarios or []

    @classmethod
    def _evaluar_tension(
        cls,
        dispositivo: Dispositivo,
        mac_raw: str,
        lectura: LecturaInstantanea,
        recorded_at: datetime,
        repo: RepositorioTelemetriaPort,
        pub: PublicadorEventosPort | None,
        log: LoggerPort | None,
    ) -> AlertaDispositivo | None:
        alerta_raw = AnalizadorCalidadEnergiaService.evaluar_alerta_tension(dispositivo.id, lectura)
        alerta = cls._filtro_persistencia.procesar_alerta(
            dispositivo.id, alerta_raw, categoria="TENSION", ahora=recorded_at
        )
        if alerta:
            cls._despachar_alerta(alerta, mac_raw, repo, pub, log, dispositivo)
        return alerta_raw

    @classmethod
    def _evaluar_desbalance(
        cls,
        dispositivo: Dispositivo,
        mac_raw: str,
        lectura: LecturaInstantanea,
        es_monofasico: bool,
        recorded_at: datetime,
        repo: RepositorioTelemetriaPort,
        pub: PublicadorEventosPort | None,
        log: LoggerPort | None,
    ) -> tuple[AlertaDispositivo | None, AlertaDispositivo | None]:
        alerta_v_raw = (
            AnalizadorCalidadEnergiaService.evaluar_alerta_desbalance(dispositivo.id, lectura)
            if not es_monofasico
            else None
        )
        alerta_v = cls._filtro_persistencia.procesar_alerta(
            dispositivo.id, alerta_v_raw, categoria="DESBALANCE_TENSION", ahora=recorded_at
        )
        if alerta_v:
            cls._despachar_alerta(alerta_v, mac_raw, repo, pub, log, dispositivo)

        alerta_i_raw = (
            AnalizadorCalidadEnergiaService.evaluar_alerta_desbalance_corriente(
                dispositivo.id, lectura, es_monofasico=es_monofasico
            )
            if not es_monofasico
            else None
        )
        alerta_i = cls._filtro_persistencia.procesar_alerta(
            dispositivo.id, alerta_i_raw, categoria="DESBALANCE_CORRIENTE", ahora=recorded_at
        )
        if alerta_i:
            cls._despachar_alerta(alerta_i, mac_raw, repo, pub, log, dispositivo)

        return alerta_v_raw, alerta_i_raw

    @classmethod
    def _evaluar_ti(
        cls,
        dispositivo: Dispositivo,
        mac_raw: str,
        lectura: LecturaInstantanea,
        recorded_at: datetime,
        repo: RepositorioTelemetriaPort,
        pub: PublicadorEventosPort | None,
        log: LoggerPort | None,
    ) -> tuple[list[AlertaDispositivo], list[AlertaDispositivo]]:
        tipo_inst = getattr(dispositivo, "tipo_instalacion", "CONSUMO")
        fases_ti_list = [f.strip().upper() for f in getattr(dispositivo, "fases_con_ti", "R,S,T").split(",")]
        alertas_ti_raw = AnalizadorCalidadEnergiaService.evaluar_alerta_ti_invertido(
            dispositivo_id=dispositivo.id,
            lectura=lectura,
            tipo_instalacion=tipo_inst,
            fases_con_ti=fases_ti_list,
        )
        for a_ti in alertas_ti_raw:
            a_filtrada = cls._filtro_persistencia.procesar_alerta(
                dispositivo.id, a_ti, categoria=f"TI_INVERTIDO_{a_ti.mensaje[:50]}", ahora=recorded_at
            )
            if a_filtrada:
                cls._despachar_alerta(a_filtrada, mac_raw, repo, pub, log, dispositivo)

        alertas_cruce_raw = AnalizadorCalidadEnergiaService.evaluar_alerta_cruce_ti(
            dispositivo_id=dispositivo.id,
            lectura=lectura,
            tipo_instalacion=tipo_inst,
            fases_con_ti=fases_ti_list,
        )
        for a_cruce in alertas_cruce_raw:
            a_filtrada = cls._filtro_persistencia.procesar_alerta(
                dispositivo.id, a_cruce, categoria=f"CRUCE_TI_{a_cruce.fase}", ahora=recorded_at
            )
            if a_filtrada:
                cls._despachar_alerta(a_filtrada, mac_raw, repo, pub, log, dispositivo)

        return alertas_ti_raw, alertas_cruce_raw

    @classmethod
    def _evaluar_fp(
        cls,
        dispositivo: Dispositivo,
        mac_raw: str,
        lectura: LecturaInstantanea,
        recorded_at: datetime,
        repo: RepositorioTelemetriaPort,
        pub: PublicadorEventosPort | None,
        log: LoggerPort | None,
    ) -> tuple[AlertaDispositivo | None, AlertaDispositivo | None]:
        alerta_raw = AnalizadorCalidadEnergiaService.evaluar_alerta_factor_potencia(dispositivo.id, lectura)
        alerta = cls._filtro_persistencia.procesar_alerta(
            dispositivo.id, alerta_raw, categoria="FACTOR_POTENCIA", ahora=recorded_at
        )
        if alerta:
            cls._despachar_alerta(alerta, mac_raw, repo, pub, log, dispositivo)

        alerta_cap_raw = AnalizadorCalidadEnergiaService.evaluar_alerta_sobrecompensacion_reactiva(
            dispositivo.id, lectura
        )
        alerta_cap = cls._filtro_persistencia.procesar_alerta(
            dispositivo.id, alerta_cap_raw, categoria="SOBRECOMPENSACION_REACTIVA", ahora=recorded_at
        )
        if alerta_cap:
            cls._despachar_alerta(alerta_cap, mac_raw, repo, pub, log, dispositivo)

        return alerta_raw, alerta_cap_raw

    @classmethod
    def _evaluar_thd(
        cls,
        dispositivo: Dispositivo,
        mac_raw: str,
        lectura: LecturaInstantanea,
        recorded_at: datetime,
        repo: RepositorioTelemetriaPort,
        pub: PublicadorEventosPort | None,
        log: LoggerPort | None,
    ) -> list[AlertaDispositivo]:
        alertas_raw = AnalizadorCalidadEnergiaService.evaluar_alertas_distorsion_armonica(dispositivo.id, lectura)
        for a_thd in alertas_raw:
            a_filtrada = cls._filtro_persistencia.procesar_alerta(
                dispositivo.id,
                a_thd,
                categoria=f"DISTORSION_ARMONICA_{a_thd.tipo_alerta}_{a_thd.fase or 'ALL'}",
                ahora=recorded_at,
            )
            if a_filtrada:
                cls._despachar_alerta(a_filtrada, mac_raw, repo, pub, log, dispositivo)
        return alertas_raw

    @classmethod
    def _auto_resolver_todas_normalizadas(
        cls,
        dispositivo_id: str,
        mac_raw: str,
        recorded_at: datetime,
        tension_raw: AlertaDispositivo | None,
        desbalance_raw: tuple[AlertaDispositivo | None, AlertaDispositivo | None],
        ti_raw: tuple[list[AlertaDispositivo], list[AlertaDispositivo]],
        fp_raw: tuple[AlertaDispositivo | None, AlertaDispositivo | None],
        thd_raw: list[AlertaDispositivo],
        repo: RepositorioTelemetriaPort,
        pub: PublicadorEventosPort | None,
        log: LoggerPort | None,
    ) -> None:
        if tension_raw is None:
            cls._auto_resolver_alertas(
                dispositivo_id, mac_raw, ["BAJA_TENSION", "SOBRETENSION", "FALTA_FASE"], recorded_at, repo, pub, log
            )
        desb_v, desb_i = desbalance_raw
        if desb_v is None:
            cls._auto_resolver_alertas(dispositivo_id, mac_raw, ["DESBALANCE_TENSION"], recorded_at, repo, pub, log)
        if desb_i is None:
            cls._auto_resolver_alertas(
                dispositivo_id,
                mac_raw,
                ["DESBALANCE_CORRIENTE", "DESBALANCE_CORRIENTE_CRITICAL"],
                recorded_at,
                repo,
                pub,
                log,
            )
        ti_inv, ti_cruce = ti_raw
        if not ti_inv:
            cls._auto_resolver_alertas(dispositivo_id, mac_raw, ["TI_INVERTIDO"], recorded_at, repo, pub, log)
        if not ti_cruce:
            cls._auto_resolver_alertas(dispositivo_id, mac_raw, ["CRUCE_TI_FASE"], recorded_at, repo, pub, log)
        fp_bajo, fp_sobrecomp = fp_raw
        if fp_bajo is None:
            cls._auto_resolver_alertas(dispositivo_id, mac_raw, ["BAJO_FACTOR_POTENCIA"], recorded_at, repo, pub, log)
        if fp_sobrecomp is None:
            cls._auto_resolver_alertas(
                dispositivo_id, mac_raw, ["SOBRECOMPENSACION_REACTIVA"], recorded_at, repo, pub, log
            )
        if not thd_raw:
            cls._auto_resolver_alertas(
                dispositivo_id,
                mac_raw,
                [
                    "ALTO_THD_TENSION_WARNING",
                    "ALTO_THD_TENSION_CRITICAL",
                    "ALTO_THD_CORRIENTE",
                    "RIESGO_RESONANCIA_CAPACITORES",
                ],
                recorded_at,
                repo,
                pub,
                log,
            )

    @classmethod
    def procesar_alertas(
        cls,
        dispositivo: Dispositivo,
        mac_raw: str,
        lectura: LecturaInstantanea,
        recorded_at: datetime,
        repo_telemetria: RepositorioTelemetriaPort,
        publicador: PublicadorEventosPort | None = None,
        logger: LoggerPort | None = None,
    ) -> None:
        tipo_instalacion = getattr(dispositivo, "tipo_instalacion", "CONSUMO")
        fases_con_ti_raw = getattr(dispositivo, "fases_con_ti", "R,S,T")
        es_monofasico = AnalizadorCalidadEnergiaService.es_instalacion_monofasica(tipo_instalacion, fases_con_ti_raw)

        t_raw = cls._evaluar_tension(dispositivo, mac_raw, lectura, recorded_at, repo_telemetria, publicador, logger)
        d_raw = cls._evaluar_desbalance(
            dispositivo, mac_raw, lectura, es_monofasico, recorded_at, repo_telemetria, publicador, logger
        )
        ti_raw = cls._evaluar_ti(dispositivo, mac_raw, lectura, recorded_at, repo_telemetria, publicador, logger)
        fp_raw = cls._evaluar_fp(dispositivo, mac_raw, lectura, recorded_at, repo_telemetria, publicador, logger)
        thd_raw = cls._evaluar_thd(dispositivo, mac_raw, lectura, recorded_at, repo_telemetria, publicador, logger)

        cls._auto_resolver_todas_normalizadas(
            dispositivo.id,
            mac_raw,
            recorded_at,
            t_raw,
            d_raw,
            ti_raw,
            fp_raw,
            thd_raw,
            repo_telemetria,
            publicador,
            logger,
        )

    _despachar_alerta = staticmethod(_despachar_alerta_fn)
    _auto_resolver_alertas = staticmethod(_auto_resolver_alertas_fn)
