# Modelado y análisis del flujo vehicular mediante teoría de colas para la optimización de tiempos de semáforo en intersecciones viales.


## Descripción

Simulador de eventos discretos de un acceso semaforizado. Los vehículos llegan
según un proceso de Poisson, esperan en una cola FIFO y se atienden de uno en
uno en 1/μ s, solo durante el verde. Con réplicas independientes e intervalos
de confianza compara configuraciones del semáforo y muestra cómo cambian la
cola y la espera según el tiempo de verde.


## Tecnologías

| Tecnología | Uso |
|---|---|
| Python 3.10+ | Lenguaje |
| NumPy | Llegadas aleatorias y métricas |
| SciPy | Intervalos de confianza (t de Student) |
| Matplotlib | Gráficas y animación |
| Tkinter | Interfaz gráfica |
| Pillow | Exportación de la animación a GIF |
| pytest | Pruebas automáticas |

## Instalación

Requisito: Python 3.10 o superior con Tkinter.

**Opción 1: entorno virtual (recomendada).** En Debian/Ubuntu, primero
`sudo apt install python3-venv python3-tk`.

```bash
cd simulacion_semaforo
python3 -m venv .venv
source .venv/bin/activate        
pip install -r requirements.txt
```

**Opción 2: paquetes del sistema (Debian/Ubuntu, sin pip).** En este caso, los
comandos se ejecutan con `python3` en lugar de `python`.

```bash
sudo apt install python3-numpy python3-scipy python3-matplotlib python3-pil python3-pytest python3-tk
```

## Ejecución

Desde `simulacion_semaforo/`, con el entorno virtual activado:

| Comando | Acción |
|---|---|
| `python main.py --gui` | Abre la interfaz gráfica |
| `python main.py` | Abre el menú de consola |

### Configuración

Los parámetros están en `config/config.json`.

Valores por defecto:

* μ = 0.5 veh/s, H = 3600 s y n = 30 réplicas.
* Confianza del 95 %.
* Semilla base 2025: la réplica i usa la semilla 2025 + i.

| Escenario | λ (veh/s) | g (s) | r (s) |
|---|---|---|---|
| Base | 0.15 | 30 | 30 |
| Verde corto | 0.15 | 20 | 40 |
| Verde largo | 0.15 | 40 | 20 |
| Demanda alta | 0.25 | 30 | 30 |
| Sobresaturado | 0.35 | 30 | 30 |

## Estructura del proyecto

**Arquitectura M-V-C**

```
simulacion_semaforo/
├── main.py                    # Punto de entrada: menú, línea de comandos e interfaz
├── config/
│   ├── config.json            # Parámetros y escenarios
│   ├── settings.py            # Carga y validación de la configuración
│   └── entorno.py             # Detección del sandbox Flatpak y de dependencias faltantes
├── model/                     # Simulación de eventos discretos
│   ├── events.py              # Tipos de evento, prioridades y agenda
│   ├── traffic_light.py       # Fases del semáforo
│   ├── arrivals.py            # Proceso de llegadas (Poisson)
│   ├── vehicle.py             # Vehículo
│   ├── simulator.py           # Motor de la simulación
│   └── statistics.py          # Métricas de una réplica
├── controller/
│   ├── experiment_service.py  # Réplicas, escenarios, comparación, barrido y pruebas
│   ├── analysis.py            # Media, desviación estándar e intervalos de confianza
│   ├── console_controller.py  # Menú de consola
│   ├── cli.py                 # Argumentos de línea de comandos
│   └── aplicacion.py          # Crea y conecta los componentes
├── view/
│   ├── console_view.py        # Tablas y mensajes de consola
│   ├── plots.py               # Gráficas
│   ├── csv_export.py          # Escritura de CSV
│   ├── exportacion.py         # Archivos que produce cada experimento
│   ├── formato.py             # Textos comunes a consola e interfaz
│   ├── style.py               # Paleta de colores
│   ├── entorno_grafico.py     # Diagnóstico del entorno gráfico de matplotlib
│   ├── animacion/             # Animación de la intersección (ventana, interfaz y GIF)
│   └── gui/                   # Interfaz gráfica: ventana, panel de escenarios y pestañas
├── tests/
│   └── test_verification.py   # Pruebas de verificación
├── docs/capturas/             # Imágenes del README
├── output/                    # Resultados generados
├── pytest.ini
└── requirements.txt
```

## Información adicional

### Funcionalidades

* Simulación de escenarios con n réplicas, semillas registradas y números
  aleatorios comunes: todas las configuraciones reciben las mismas llegadas.
* Indicadores con media ± intervalo de confianza:
  * cola media Q̄ y cola máxima;
  * espera en cola Wq y tiempo en el sistema W;
  * capacidad efectiva C;
  * cola residual al final de cada verde.
* Comparación porcentual de cada escenario con la base (misma λ).
* Barrido del tiempo de verde g con ciclo fijo (Tabla I y Fig. 2 del informe).
* Traza de eventos y vehículos atendidos por ciclo.
* Animación de la intersección con pausa y reinicio, exportable a GIF.
* 9 pruebas de verificación: balance de vehículos, ninguna salida en rojo,
  reproducibilidad, capacidad por verde, orden de eventos, sobresaturación y
  validación de entradas.
* Resultados en `output/`:
  * CSV de resumen, réplicas, ciclos, traza, comparación y barrido;
  * 7 gráficas PNG.

### Modelo

* Un acceso, con una cola FIFO sin límite de capacidad y un servidor.
* Semáforo de tiempo fijo: verde g, rojo r y ciclo T = g + r. La simulación
  empieza en rojo.
* Servicio determinista de 1/μ s, solo en verde y solo si termina antes de
  que acabe el verde.
* Q(t) cuenta los vehículos en espera, sin el que está en servicio.
* Orden de los eventos simultáneos: salida → cambio de fase → llegada.
* ρef = λT/(μg) compara la demanda por ciclo con la capacidad del verde. Con
  ρef ≥ 1 la cola puede crecer ciclo a ciclo.

### Limitaciones

* No se ha validado con datos de campo, y μ = 0.5 veh/s es un dato sintético.
* Se modela un solo acceso. Con T fijo, más verde siempre reduce su cola, por
  eso el mejor g del barrido es siempre el mayor probado. No es una
  optimización de toda la intersección.
* No hay fase amarilla, por el tiempo perdido al arrancar y para una abstracción mas simple del modelo.

### Capturas

| Resultados | Gráficas |
|---|---|
| ![Pestaña Resultados](docs/capturas/resultados.png) | ![Pestaña Gráficas](docs/capturas/graficas.png) |
| **Barrido de g** | **Animación** |
| ![Pestaña Barrido de g](docs/capturas/barrido.png) | ![Pestaña Animación](docs/capturas/animacion.png) |

### Autores

- Juan Calopino
- Daniel Saavedra
- Anthony Yaguana
- Odalis Rosillo.
  
**Universidad Nacional de Loja - Computación**
