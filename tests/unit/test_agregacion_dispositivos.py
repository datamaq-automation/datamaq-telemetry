"""tests/unit/test_agregacion_dispositivos.py — parser y agregación de dispositivos."""

import pytest

from src.application.use_cases.agregacion_dispositivos import _parsear_relacion_transformacion


class TestParsearRelacionTransformacion:
    """Casos de parseo de relación de tensión para transformadores MT/BT."""

    def test_relacion_basica_sin_espacios(self):
        """Parsea "13.2/0.4" correctamente."""
        assert _parsear_relacion_transformacion("13.2/0.4") == pytest.approx(33.0)

    def test_relacion_con_espacios(self):
        """Tolera espacios alrededor de la barra divisoria."""
        assert _parsear_relacion_transformacion("13.2 / 0.4") == pytest.approx(33.0)

    def test_relacion_con_sufijo_kv(self):
        """Tolera sufijo de unidad "kV" en ambas partes."""
        assert _parsear_relacion_transformacion("13.2 kV / 0.4 kV") == pytest.approx(33.0)

    def test_relacion_minuscula_kv(self):
        """Tolera minúsculas en el sufijo de unidad."""
        assert _parsear_relacion_transformacion("13.2 kv / 0.4 kv") == pytest.approx(33.0)

    def test_relacion_solo_v_sufijo(self):
        """Tolera sufijo "V" en vez de "kV"."""
        assert _parsear_relacion_transformacion("13.2 V / 0.4 V") == pytest.approx(33.0)

    def test_relacion_mixta_sufijos(self):
        """Tolera sufijos distintos en cada lado."""
        assert _parsear_relacion_transformacion("13.2 kV / 400 V") == pytest.approx(0.033)

    def test_ninguno_retorna_uno(self):
        """Retorna 1.0 si no hay relación (None)."""
        assert _parsear_relacion_transformacion(None) == 1.0

    def test_vacio_retorna_uno(self):
        """Retorna 1.0 si la cadena está vacía."""
        assert _parsear_relacion_transformacion("") == 1.0

    def test_falta_segundo_termino_retorna_uno(self):
        """Retorna 1.0 si falta el numerador o denominador."""
        assert _parsear_relacion_transformacion("13.2") == 1.0

    def test_division_por_cero_retorna_uno(self):
        """Retorna 1.0 si el divisor es cero."""
        assert _parsear_relacion_transformacion("13.2/0") == 1.0
        assert _parsear_relacion_transformacion("13.2/0.0") == 1.0

    def test_multiple_barras_retorna_uno(self):
        """Retorna 1.0 si hay más de una barra divisoria."""
        assert _parsear_relacion_transformacion("13.2/0.4/extra") == 1.0

    def test_texto_invalido_retorna_uno(self):
        """Retorna 1.0 si el formato es completamente inválido."""
        assert _parsear_relacion_transformacion("abc/def") == 1.0

    def test_barra_al_inicio_retorna_uno(self):
        """Retorna 1.0 si la barra está al inicio."""
        assert _parsear_relacion_transformacion("/13.2") == 1.0

    def test_barra_al_final_retorna_uno(self):
        """Retorna 1.0 si la barra está al final."""
        assert _parsear_relacion_transformacion("13.2/") == 1.0
