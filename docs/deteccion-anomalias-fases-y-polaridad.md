# Detección de Anomalías Eléctricas: Orden de Fases y Sentido de Transformadores de Corriente (TIs)

Este documento detalla la investigación técnica y las reglas matemáticas para detectar en la plataforma **Datamaq Telemetry** anomalías de instalación física en medidores **Powermeter**:
1. **Sentido / Polaridad de los Transformadores de Corriente (TI Invertido).**
2. **Cruce de TIs entre Fases distintas (CT Mismatch).**
3. **Secuencia / Orden de Fases (Directa $R-S-T$ vs. Inversa $R-T-S$).**

---

## 1. Detección de Sentido / Polaridad de TIs (TI Invertido)

### 1.1 Fundamento Físico
Cada transformador de corriente tipo toroidal o Split-Core (núcleo abierto) posee un sentido de montaje indicado por una flecha o las marcas de bornes:
* **Lado Primario:** $P_1 \to P_2$ o $K \to L$ (la flecha debe apuntar desde la red distribuidora hacia la carga consumidora).
* **Lado Secundario:** Bornes $s_1 - s_2$ conectados a los canales analógicos del Powermeter.

Si el instalador monta el sensor físicamente al revés, o intercambia los cables secundario $s_1$ y $s_2$:
$$\vec{I}_{medida} = -\vec{I}_{real} = \vec{I}_{real} \angle 180^\circ$$

### 1.2 Manifestación en la Telemetría
* **Potencia Activa:** Pasa a ser negativa ($P_k < 0$), simulando una generación o exportación de energía inexistente.
* **Potencia Reactiva:** Invierte su signo ($Q_k \to -Q_k$).
* **Potencia Aparente:** Se mantiene positiva ($S_k > 0$).
* **Factor de Potencia:** Se ubica en los cuadrantes II o III (generación aparente, $-1.0 \le FP_k < 0$).
* **Potencia Activa Total:** $P_{total} = P_R + P_S + P_T$ resulta drásticamente menor a la real porque la fase invertida resta potencia en lugar de sumarla.

```
                  ┌────────────────────────────────────────────────────────┐
                  │                 DIAGNÓSTICO DE POLARIDAD               │
                  └────────────────────────────────────────────────────────┘
                    Normal (Consumo)              TI Invertido (Error)
                    ────────────────             ─────────────────────
                    I_R = 120.0 A                 I_R = 120.0 A
                    V_R = 224.0 V                 V_R = 224.0 V
                    P_R = +26.2 kW  (✓)           P_R = -26.2 kW  (❌ ALERTA)
                    FP_R = 0.97                   FP_R = -0.97 (Cuadrante II)
```

### 1.3 Algoritmo de Detección en Dominio
Para evitar falsas alarmas provocadas por ruido residual cuando la fase está en vacío ($I < 2\text{ A}$), se define una guarda de corriente y potencia:

$$\text{Condición de TI Invertido en Fase } k: \quad (I_k \ge I_{min}) \land (P_k \le -P_{umbral}) \land (P_{total\_otras\_fases} > 0)$$

* **Parámetros Recomendados:**
  * $I_{min} = 5.0\text{ A}$
  * $P_{umbral} = 500\text{ W}$
* **Tipo de Alerta:** `TI_INVERTIDO`
* **Severidad:** `WARNING`
* **Mensaje:** `"Posible inversión de polaridad en Transformador de Corriente (TI) de Fase {fase}: P={P_k}W con I={I_k}A."`

---

## 2. Detección de Cruce de TIs entre Fases (CT Mismatch)

### 2.1 Fundamento Físico
Ocurre cuando el sensor toroidal colocado en el conductor de la Fase S se conecta en la bornera correspondiente a la Fase R del medidor.

### 2.2 Manifestación en la Telemetría
La tensión $V_R$ y la corriente $I_S$ tienen un desfase espacial inherente de $120^\circ$.
* El factor de potencia aparente calculado $FP = \cos(120^\circ \pm \phi)$ cae a valores anormalmente bajos ($\approx 0.0$ a $0.5$) incluso en cargas con factor de potencia unitario.
* La potencia activa calculada por el hardware es errática y no se condice con el producto $V \cdot I$.

### 2.3 Algoritmo de Detección
$$\text{Si } (I_k > 10\text{ A}) \land (|FP_k| < 0.40) \land (|FP_{promedio\_otras}| > 0.85) \implies \mathbf{ALERTA: \text{Cruce de TI en Fase } k}$$

---

## 3. Detección de Secuencia y Orden de Fases ($R-S-T$ vs $R-T-S$)

### 3.1 Fundamento Físico
La secuencia de fases define el orden cronológico en que las ondas senoidales de tensión alcanzan sus crestas positivas:
* **Secuencia Directa / Positiva ($R \to S \to T$):** Desfases de $0^\circ, -120^\circ, +120^\circ$.
* **Secuencia Inversa / Negativa ($R \to T \to S$):** Desfases de $0^\circ, +120^\circ, -120^\circ$.

### 3.2 Riesgo Industrial
En motores asíncronos trifásicos (bombas, extractores, compresores, cintas), una inversión en la secuencia de fases provoca la **rotación en sentido contrario**, lo que puede ocasionar daños mecánicos severos y fallas de lubricación.

### 3.3 Estrategia de Implementación en Datamaq Telemetry

#### Nivel A: Desde el Firmware Powermeter (Hardware ESP32)
El circuito analógico del medidor (mediante detector de cruce por cero ZCD o DSP) puede determinar el tiempo entre los pasos por cero de $V_R, V_S, V_T$:
* Si $t(V_S) - t(V_R) \approx 6.66\text{ ms}$ (a 50 Hz) $\implies$ **Directa ($R-S-T$)**.
* Si $t(V_T) - t(V_R) \approx 6.66\text{ ms}$ $\implies$ **Inversa ($R-T-S$)**.
* El payload MQTT `m/wifi/{UID}/status` o `inst` puede incluir el campo `"seq": "RST" | "RTS"`.

#### Nivel B: Análisis Backend por Componentes Simétricas (Transformada de Fortescue)
Si el medidor envía las tensiones complejas o tensiones de línea $V_{RS}, V_{ST}, V_{TR}$:
$$V_1 = \frac{1}{3}(V_R + a V_S + a^2 V_T) \quad (\text{Secuencia Positiva})$$
$$V_2 = \frac{1}{3}(V_R + a^2 V_S + a V_T) \quad (\text{Secuencia Negativa})$$
donde $a = e^{j 120^\circ} = -\frac{1}{2} + j \frac{\sqrt{3}}{2}$.
* **Si $V_2 > V_1$:** La secuencia está invertida.

---

## 4. Hoja de Ruta y Estado de Implementación

| Fase | Feature | Capa | Estado |
| :--- | :--- | :--- | :---: |
| **1** | Cálculo de Corriente de Neutro Estimada ($I_N$) | Dominio + DB + API | ✅ **Implementado** |
| **2** | Categorización de Instalación (`CONSUMO`, `GENERACION_FV`, `MIXTO`) | Dominio + DB + API | ✅ **Implementado** |
| **3** | Ausencia física de TIs (`fases_con_ti`: `"R,S,T"`, `"S,T"`, etc.) | Dominio + DB + API | ✅ **Implementado** |
| **4** | Detección de TI Invertido ($P_k \le -500\text{W}, I_k \ge 5\text{A}$) con Alerta de Dominio | `AnalizadorCalidadEnergiaService` | ✅ **Implementado** |
| **5** | Corrección por Software de Polaridad de TIs | Web UI ESP32 (`192.168.4.1`) | 💡 *Operativo en Hardware* |
| **6** | Reporte Nativo de Secuencia de Fases en Tópico MQTT `status` | Firmware Powermeter + Worker | 📋 *Especificado* |
| **7** | Panel de Diagnóstico de Instalación en Frontend | SPA (`app-datamaq`) | 📋 *Especificado* |
