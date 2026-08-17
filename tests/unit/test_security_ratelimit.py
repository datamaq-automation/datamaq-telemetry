"""Fase G1 — Rate limiter de login singleton y eviction por tope de claves."""

from src.domain.auth.services import RateLimiterService
from src.infrastructure.fastapi import dependencies as deps


def test_get_rate_limiter_es_singleton():
    primero = deps.get_rate_limiter()
    segundo = deps.get_rate_limiter()
    assert primero is segundo


def test_rate_limiter_eviction_por_tope():
    limiter = RateLimiterService(max_intentos=5, ventana_segundos=60)
    limiter.MAX_CLAVES = 2

    limiter.registrar_intento("clave-1")
    limiter.registrar_intento("clave-2")
    limiter.registrar_intento("clave-3")

    assert "clave-1" not in limiter._intentos
    assert "clave-2" in limiter._intentos
    assert "clave-3" in limiter._intentos
    assert len(limiter._intentos) == 2


def test_rate_limiter_compartido_bloquea_tras_exceder():
    limiter = deps.get_rate_limiter()
    limiter.resetear("atacante")
    for _ in range(limiter.max_intentos):
        limiter.registrar_intento("atacante")
    assert limiter.permitir("atacante") is False
