# PromptKit

**Toolkit de ingeniería de prompts para la línea de comandos.**  
Corre prompts contra Claude, prueba en lote, compara versiones A/B, y rastrea la calidad con el tiempo — todo desde la terminal, sin escribir código.

---

## Índice

1. [Instalación](#1-instalación)
2. [Configuración de la API key](#2-configuración-de-la-api-key)
3. [Estructura del proyecto](#3-estructura-del-proyecto)
4. [Formato del archivo YAML de prompt](#4-formato-del-archivo-yaml-de-prompt)
5. [Comandos](#5-comandos)
   - [run — correr un prompt](#51-run--correr-un-prompt)
   - [chat — loop interactivo continuo](#52-chat--loop-interactivo-continuo)
   - [batch — múltiples entradas a la vez](#53-batch--múltiples-entradas-a-la-vez)
   - [compare — comparar dos prompts A/B](#54-compare--comparar-dos-prompts-ab)
   - [history — historial de calidad](#55-history--historial-de-calidad)
   - [new — crear un nuevo prompt](#56-new--crear-un-nuevo-prompt)
6. [Modelos disponibles](#6-modelos-disponibles)
7. [Cómo se calcula la calidad](#7-cómo-se-calcula-la-calidad)
8. [Dónde se guardan los resultados](#8-dónde-se-guardan-los-resultados)
9. [Modo mock (sin gastar créditos)](#9-modo-mock-sin-gastar-créditos)
10. [Prompts de ejemplo incluidos](#10-prompts-de-ejemplo-incluidos)
11. [Preguntas frecuentes](#11-preguntas-frecuentes)

---

## 1. Instalación

Requiere **Python 3.10+**.

```bash
# Clona o descarga el proyecto, entra a la carpeta
cd PromptKit

# Instala todas las dependencias y el comando promptkit
pip install -e .
```

Dependencias que se instalan automáticamente:

| Paquete | Para qué sirve |
|---------|----------------|
| `anthropic` | Llamadas a la API de Claude |
| `pyyaml` | Leer archivos de prompt `.yaml` |
| `click` | Interfaz de línea de comandos |
| `rich` | Tablas y colores en la terminal |
| `pydantic` | Validación de datos |
| `python-dotenv` | Leer la API key desde `.env` |

---

## 2. Configuración de la API key

Crea un archivo `.env` en la raíz del proyecto:

```
ANTHROPIC_API_KEY=sk-ant-api03-TU-CLAVE-AQUI
```

O bien expórtala directamente en tu terminal:

```bash
# Windows PowerShell
$env:ANTHROPIC_API_KEY = "sk-ant-api03-..."

# macOS / Linux / Git Bash
export ANTHROPIC_API_KEY="sk-ant-api03-..."
```

> El archivo `.env` se carga automáticamente cada vez que usas PromptKit. Nunca lo subas a Git — ya está en `.gitignore`.

---

## 3. Estructura del proyecto

```
PromptKit/
│
├── prompts/                        ← Tus archivos de prompt (.yaml)
│   ├── example_classifier.yaml     ← Clasifica texto en categorías
│   └── example_extractor.yaml      ← Extrae datos estructurados
│
├── inputs/                         ← Archivos de entrada para batch/compare
│   └── example_inputs.json         ← 5 casos de prueba de ejemplo
│
├── results/                        ← Se crea automáticamente
│   └── 2026-05-17/                 ← Carpeta por fecha
│       ├── example_classifier.json ← Resultados del día
│       └── example_extractor.json
│
├── promptkit/                      ← Código fuente
│   ├── evaluator.py                ← Motor principal (run, batch, compare, judge)
│   ├── storage.py                  ← Guardar y leer resultados
│   └── cli.py                      ← Todos los comandos de la terminal
│
├── .env                            ← Tu API key (no subir a Git)
├── .env.example                    ← Ejemplo de configuración
├── requirements.txt
├── setup.py
└── README.md
```

---

## 4. Formato del archivo YAML de prompt

Cada prompt vive en un archivo `.yaml` dentro de `prompts/`. Este es el formato completo:

```yaml
version: "1.0"               # Versión del prompt (para historial)
name: mi_clasificador         # Nombre único (sin espacios)
description: Clasifica emails en categorías de soporte
model: claude-haiku-4-5-20251001  # Modelo por defecto
max_tokens: 512               # Máximo de tokens en la respuesta

system_prompt: |
  Eres un experto en clasificación de texto.
  Responde ÚNICAMENTE con JSON válido. Sin texto extra.

user_template: |
  Clasifica el siguiente texto:

  Texto: {texto}
  Idioma: {idioma}

  Devuelve JSON con esta estructura:
  {
    "categoria": "...",
    "confianza": 0.0
  }

expected_output_fields:      # Campos que debe tener el JSON de respuesta
  - categoria
  - confianza
```

### Variables del template

Escribe `{nombre_variable}` en `user_template` donde quieras insertar texto.
Al correr el prompt, PromptKit te preguntará por cada variable.

```
user_template: |
  Analiza este email de {remitente}:
  {cuerpo_email}
```

Aquí `{remitente}` y `{cuerpo_email}` son las dos variables que se pedirán.

> **Nota:** Los `{…}` que forman parte del JSON de ejemplo en el template (como `{"campo": "valor"}`) no se interpretan como variables — PromptKit los distingue automáticamente.

---

## 5. Comandos

Todos los comandos se ejecutan con:

```bash
python -m promptkit.cli <comando> [opciones]
```

O si `promptkit` está en tu PATH después de `pip install -e .`:

```bash
promptkit <comando> [opciones]
```

---

### 5.1 `run` — Correr un prompt

Ejecuta un prompt una sola vez.

```bash
python -m promptkit.cli run prompts/example_classifier.yaml
```

**Sin opciones:** PromptKit detecta las variables del YAML y te las pide directamente en la terminal:

```
Este prompt necesita 1 variable(s). Escribe cada una:

  text  (escribe tu texto; línea vacía para terminar)
  > El servidor cayó a las 3am y perdimos todas las sesiones de usuario
  >
  ← línea vacía + Enter para enviar

┌─────────────────────────────┐
│ Running: example_classifier │
└─────────────────────────────┘
Model:            claude-haiku-4-5-20251001
Latency:          843 ms
Tokens:           187 in / 94 out
Cost:             $0.000165
Quality score:    0.920
Valid JSON:       ✓
Required fields:  ✓
┌────────────────── Parsed Output ──────────────────┐
│ {                                                 │
│   "category": "technical_issue",                  │
│   "confidence": 0.97,                             │
│   "reasoning": "Describe una caída de servidor.", │
│   "keywords": ["servidor", "3am", "sesiones"]     │
│ }                                                 │
└───────────────────────────────────────────────────┘
```

**Opciones disponibles:**

| Opción | Descripción |
|--------|-------------|
| *(sin opciones)* | Modo interactivo — pide las variables en la terminal |
| `--input '{"text":"..."}'` | Pasa las variables como JSON en línea |
| `--input-file ruta.json` | Lee las variables desde un archivo JSON |
| `--model claude-sonnet-4-6` | Usa un modelo diferente al del YAML |
| `--mock` | Respuesta simulada, sin llamar a la API |
| `--no-save` | No guardar el resultado en `results/` |

**Ejemplos:**

```bash
# Modo interactivo (recomendado para uso diario)
python -m promptkit.cli run prompts/example_classifier.yaml

# Con modelo más potente
python -m promptkit.cli run prompts/example_classifier.yaml --model claude-sonnet-4-6

# Desde archivo (útil en Windows donde las comillas son difíciles)
python -m promptkit.cli run prompts/example_classifier.yaml --input-file inputs/example_inputs.json

# Sin guardar
python -m promptkit.cli run prompts/example_classifier.yaml --no-save
```

---

### 5.2 `chat` — Loop interactivo continuo

Corre el mismo prompt repetidamente en un loop. Escribes un texto, ves el resultado, escribes otro, sin volver a ejecutar el comando.

```bash
python -m promptkit.cli chat prompts/example_classifier.yaml
```

**Cómo funciona:**

```
┌────────────────────────────────────────────────────┐
│ Chat mode: example_classifier (claude-haiku-4-5...) │
│ Variables: text                                     │
│ Escribe tus respuestas. Presiona Ctrl+C para salir. │
└────────────────────────────────────────────────────┘

──────────────────── Corrida #1 ────────────────────
  text  (escribe tu texto; línea vacía para terminar)
  > Me cobraron dos veces mi suscripción mensual
  >
[... resultado del análisis ...]

──────────────────── Corrida #2 ────────────────────
  text  (escribe tu texto; línea vacía para terminar)
  > Necesito exportar mis datos en formato CSV
  >
[... resultado del análisis ...]

^^C

Saliendo. 2 corridas completadas.
```

**Reglas del input:**
- Escribe una o varias líneas
- **Línea vacía + Enter** = enviar el texto al prompt
- **Ctrl+C** = salir del loop

**Opciones disponibles:**

| Opción | Descripción |
|--------|-------------|
| `--model claude-sonnet-4-6` | Modelo a usar (anula el del YAML) |
| `--mock` | Respuestas simuladas, sin API |
| `--no-save` | No guardar resultados en disco |

**Ejemplos:**

```bash
# Chat básico
python -m promptkit.cli chat prompts/example_classifier.yaml

# Con modelo específico
python -m promptkit.cli chat prompts/example_extractor.yaml --model claude-opus-4-7

# Modo exploración sin guardar nada
python -m promptkit.cli chat prompts/example_classifier.yaml --no-save
```

> **Tip:** Usa `chat` cuando quieras probar muchos textos seguidos y ver cómo responde el prompt. Es mucho más rápido que ejecutar `run` una y otra vez.

---

### 5.3 `batch` — Múltiples entradas a la vez

Corre el mismo prompt contra una lista de entradas de un archivo JSON y muestra una tabla resumen.

```bash
python -m promptkit.cli batch prompts/example_classifier.yaml --file inputs/example_inputs.json
```

**Formato del archivo de entradas** (`inputs/example_inputs.json`):

```json
[
  { "text": "El servidor cayó a las 3am" },
  { "text": "Me cobraron dos veces" },
  { "text": "Quisiera una opción de modo oscuro" },
  { "text": "¿Tienen período de prueba gratuito?" },
  { "text": "La función de exportar lleva rota dos semanas" }
]
```

Cada objeto del array corresponde a las variables que usa el `user_template`. Si tu prompt tiene `{tema}` y `{idioma}`, cada objeto debe tener `"tema"` e `"idioma"`.

**Salida de ejemplo:**

```
╭─────────────────────────────────────────────────────────────────────╮
│ Batch run: example_classifier  (5 inputs)                           │
╰─────────────────────────────────────────────────────────────────────╯

 Batch Run Results
╭───┬─────────────────────────────────────┬─────────────┬──────────────┬──────────┬─────────┬──────┬────────╮
│ # │ Input (truncated)                   │ Latency(ms) │ Tokens In/Out│ Cost ($) │ Quality │ JSON │ Fields │
├───┼─────────────────────────────────────┼─────────────┼──────────────┼──────────┼─────────┼──────┼────────┤
│ 1 │ {'text': 'El servidor cayó a las …  │         843 │    187 / 94  │ 0.000165 │   0.920 │  ✓   │   ✓    │
│ 2 │ {'text': 'Me cobraron dos veces'…   │         612 │    163 / 88  │ 0.000151 │   0.905 │  ✓   │   ✓    │
│ 3 │ {'text': 'Quisiera una opción de…   │         731 │    171 / 91  │ 0.000157 │   0.878 │  ✓   │   ✓    │
│ 4 │ {'text': '¿Tienen período de prue…  │         508 │    158 / 86  │ 0.000147 │   0.893 │  ✓   │   ✓    │
│ 5 │ {'text': 'La función de exportar…   │         692 │    175 / 93  │ 0.000161 │   0.911 │  ✓   │   ✓    │
╰───┴─────────────────────────────────────┴─────────────┴──────────────┴──────────┴─────────┴──────┴────────╯

Aggregate: 5 runs | avg quality 0.901 | avg latency 677ms | valid JSON 100% | total cost $0.00078
```

**Opciones disponibles:**

| Opción | Descripción |
|--------|-------------|
| `--file ruta.json` | *(requerido)* Archivo con la lista de entradas |
| `--model claude-sonnet-4-6` | Modelo a usar |
| `--mock` | Respuestas simuladas |
| `--no-save` | No guardar resultados |

---

### 5.4 `compare` — Comparar dos prompts A/B

Corre dos prompts con las mismas entradas y determina cuál es mejor, mostrando métricas lado a lado y un veredicto con justificación.

```bash
python -m promptkit.cli compare \
  prompts/example_classifier.yaml \
  prompts/example_extractor.yaml \
  --file inputs/example_inputs.json
```

**Salida de ejemplo:**

```
╭──────────────────────────────────────────────────────────────────────╮
│ Comparing: example_classifier vs example_extractor  (5 inputs each) │
╰──────────────────────────────────────────────────────────────────────╯

                        Comparison Results
╭──────────────────────┬────────────────────┬───────────────────╮
│ Metric               │ example_classifier │ example_extractor │
├──────────────────────┼────────────────────┼───────────────────┤
│ Avg Quality Score    │          0.912     │         0.887     │  ← verde = ganador
│ Valid JSON Rate      │            1.0     │           1.0     │
│ Required Fields Rate │            1.0     │           1.0     │
│ Avg Latency (ms)     │          677.4     │         724.1     │
│ Total Cost ($)       │       0.00078      │        0.00081    │
│ Avg Input Tokens     │          170.8     │         163.2     │
│ Avg Output Tokens    │           90.4     │          98.6     │
│ Error Count          │              0     │             0     │
╰──────────────────────┴────────────────────┴───────────────────╯

╭────────────────────────────── Verdict ────────────────────────────────╮
│ Winner: example_classifier                                            │
│                                                                       │
│ example_classifier scores higher (composite 0.956 vs 0.944).         │
│ Quality: 0.912 vs 0.887, Valid JSON: 1.0 vs 1.0.                     │
╰───────────────────────────────────────────────────────────────────────╯
```

**Cómo se elige el ganador:**

El sistema calcula un puntaje compuesto para cada prompt:

```
puntaje = (calidad × 0.50) + (JSON válido × 0.25) + (campos requeridos × 0.25)
```

Si hay empate exacto, gana el que tenga menor latencia promedio.

**Opciones disponibles:**

| Opción | Descripción |
|--------|-------------|
| `--file ruta.json` | *(requerido)* Entradas de prueba |
| `--model claude-sonnet-4-6` | Mismo modelo para ambos prompts |
| `--model-a claude-haiku-4-5-20251001` | Modelo solo para el prompt A |
| `--model-b claude-opus-4-7` | Modelo solo para el prompt B |
| `--mock` | Respuestas simuladas |
| `--no-save` | No guardar resultados |

**Caso de uso típico — comparar el mismo prompt en dos modelos:**

```bash
python -m promptkit.cli compare \
  prompts/example_classifier.yaml \
  prompts/example_classifier.yaml \
  --file inputs/example_inputs.json \
  --model-a claude-haiku-4-5-20251001 \
  --model-b claude-sonnet-4-6
```

Esto corre el mismo prompt dos veces con modelos diferentes para comparar calidad vs costo.

---

### 5.5 `history` — Historial de calidad

Muestra todos los resultados guardados para un prompt y la tendencia del puntaje de calidad con el tiempo.

```bash
python -m promptkit.cli history example_classifier
```

**Salida de ejemplo:**

```
           History — example_classifier
╭────────────┬───────────────────────────┬─────────┬──────┬──────────────┬──────────╮
│ Date       │ Model                     │ Quality │ JSON │ Latency (ms) │ Cost ($) │
├────────────┼───────────────────────────┼─────────┼──────┼──────────────┼──────────┤
│ 2026-05-15 │ claude-haiku-4-5-20251001 │   0.872 │  ✓   │          843 │ 0.000165 │
│ 2026-05-16 │ claude-haiku-4-5-20251001 │   0.891 │  ✓   │          712 │ 0.000158 │
│ 2026-05-17 │ claude-sonnet-4-6         │   0.943 │  ✓   │          634 │ 0.001240 │
╰────────────┴───────────────────────────┴─────────┴──────┴──────────────┴──────────╯

Trend over 3 runs: ↑ improving (+0.071)
```

El argumento es el **nombre del prompt** (sin `.yaml`), que debe coincidir con el campo `name` dentro del YAML.

---

### 5.6 `new` — Crear un nuevo prompt

Crea un nuevo archivo `.yaml` de prompt de forma interactiva, preguntando cada campo paso a paso.

```bash
python -m promptkit.cli new mi_resumidor
```

**Flujo del asistente:**

```
╭──────────────────────────────────╮
│ New prompt: mi_resumidor         │
╰──────────────────────────────────╯

Description: Resume texto en 3 puntos clave
Model (claude-haiku-4-5-20251001, claude-sonnet-4-6, claude-opus-4-7) [claude-haiku-4-5-20251001]:
Max tokens [512]:
System prompt (one line; use \n for newlines): Eres un experto en síntesis.\nSé conciso y claro.
User template (use {var} placeholders) [Process the following: {text}]: Resume el siguiente texto en exactamente 3 puntos:\n\n{texto}
Expected output JSON fields (comma-separated): puntos, resumen_breve

Created: C:\Users\...\PromptKit\prompts\mi_resumidor.yaml
```

Después de crearlo, puedes usarlo inmediatamente:

```bash
python -m promptkit.cli chat prompts/mi_resumidor.yaml
```

---

## 6. Modelos disponibles

| ID del modelo | Alias corto | Velocidad | Calidad | Costo (entrada/salida por token) |
|---------------|-------------|-----------|---------|-----------------------------------|
| `claude-haiku-4-5-20251001` | `haiku` | ★★★ | ★★ | $0.00000025 / $0.00000125 |
| `claude-sonnet-4-6` | `sonnet` | ★★ | ★★★ | $0.000003 / $0.000015 |
| `claude-opus-4-7` | `opus` | ★ | ★★★★ | $0.000015 / $0.000075 |

**¿Cuál usar?**

- **Haiku** — Para desarrollo, pruebas rápidas, o cuando el volumen es alto y el presupuesto es ajustado. Ideal para clasificación y extracción simples.
- **Sonnet** — Para producción general. Mejor balance calidad/precio.
- **Opus** — Para tareas complejas que requieren razonamiento profundo, análisis jurídico, código complejo, etc.

El modelo se puede definir en el YAML (`model: claude-sonnet-4-6`) y sobreescribir en cualquier comando con `--model`.

---

## 7. Cómo se calcula la calidad

Cada resultado incluye un **quality score** entre 0.0 y 1.0. Este puntaje lo genera un modelo de IA (Haiku) que actúa como juez imparcial evaluando:

- Si la respuesta cumple con la tarea descrita
- Si el formato es correcto
- Si los campos están completos y coherentes

| Puntaje | Significado |
|---------|-------------|
| 0.9 – 1.0 | Excelente — cumple todos los criterios |
| 0.7 – 0.89 | Bueno — cumple la mayoría con detalles menores |
| 0.4 – 0.69 | Regular — cumple parcialmente |
| 0.0 – 0.39 | Malo — falla en criterios fundamentales |

Además del quality score, cada resultado valida:

- **Valid JSON** ✓/✗ — Si la respuesta es JSON parseable
- **Required fields** ✓/✗ — Si el JSON contiene todos los campos de `expected_output_fields`

---

## 8. Dónde se guardan los resultados

Los resultados se guardan automáticamente (a menos que uses `--no-save`) en:

```
results/
└── YYYY-MM-DD/
    └── nombre_del_prompt.json
```

Cada archivo JSON contiene una lista de runs. Ejemplo de un registro:

```json
{
  "version": "1.0",
  "model": "claude-haiku-4-5-20251001",
  "latency_ms": 843.21,
  "input_tokens": 187,
  "output_tokens": 94,
  "cost_usd": 0.0001648,
  "quality_score": 0.92,
  "is_valid_json": true,
  "has_required_fields": true,
  "raw_output": "{\"category\": \"technical_issue\", ...}",
  "parsed_output": { "category": "technical_issue", "confidence": 0.97, ... },
  "prompt_name": "example_classifier",
  "input_vars": { "text": "El servidor cayó a las 3am" },
  "error": null
}
```

Usa `promptkit history <nombre>` para ver el historial en una tabla y ver si tu prompt mejora o empeora con el tiempo.

---

## 9. Modo mock (sin gastar créditos)

Todos los comandos aceptan `--mock`. En este modo no se hace ninguna llamada a la API — se devuelve una respuesta simulada predefinida.

```bash
python -m promptkit.cli run prompts/example_classifier.yaml --mock
python -m promptkit.cli chat prompts/example_classifier.yaml --mock
python -m promptkit.cli batch prompts/example_classifier.yaml --file inputs/example_inputs.json --mock
python -m promptkit.cli compare prompts/example_classifier.yaml prompts/example_extractor.yaml --file inputs/example_inputs.json --mock
```

Útil para:
- Verificar que el YAML está bien escrito
- Probar la interfaz sin consumir créditos
- Desarrollo y CI/CD

---

## 10. Prompts de ejemplo incluidos

### `example_classifier.yaml`

Clasifica cualquier texto en una de estas categorías:

| Categoría | Cuándo se usa |
|-----------|---------------|
| `technical_issue` | Caídas de servidor, bugs, errores de infraestructura |
| `billing` | Cobros, facturas, suscripciones, precios |
| `feature_request` | Nuevas funciones, mejoras, sugerencias de producto |
| `general_inquiry` | Preguntas generales, solicitudes de información |
| `complaint` | Quejas, insatisfacción, feedback negativo |

**Salida:**
```json
{
  "category": "technical_issue",
  "confidence": 0.97,
  "reasoning": "El texto describe una caída de servidor.",
  "keywords": ["servidor", "3am", "sesiones"]
}
```

**Uso:**
```bash
python -m promptkit.cli run prompts/example_classifier.yaml
# → te pregunta el texto directamente
```

---

### `example_extractor.yaml`

Extrae entidades y datos estructurados de cualquier texto.

**Salida:**
```json
{
  "subject": "Incidente de servidor",
  "sentiment": "negative",
  "entities": {
    "people": ["ingeniero de guardia"],
    "organizations": [],
    "locations": [],
    "dates": ["3am"]
  },
  "key_facts": [
    "El servidor cayó a las 3am",
    "Se perdieron todas las sesiones de usuario",
    "45 minutos para restaurar el servicio"
  ],
  "action_required": true
}
```

**Uso:**
```bash
python -m promptkit.cli chat prompts/example_extractor.yaml
# → loop continuo para extraer datos de varios textos
```

---

## 11. Preguntas frecuentes

**¿Puedo tener mis prompts en otra carpeta?**  
Sí. Todos los comandos aceptan rutas absolutas o relativas:
```bash
python -m promptkit.cli run C:\MisPrompts\mi_prompt.yaml
```

**¿Puedo usar variables que no sean `text`?**  
Sí. Puedes tener cualquier número de variables con cualquier nombre:
```yaml
user_template: |
  Analiza el email de {remitente} sobre {asunto}:
  {cuerpo}
```
PromptKit detectará `remitente`, `asunto` y `cuerpo` y te los pedirá uno por uno.

**¿Por qué el quality score varía entre corridas del mismo texto?**  
El juez de calidad es un modelo de IA, y los LLMs tienen algo de varianza en sus respuestas. Para obtener puntajes más estables, usa `batch` con el mismo input varias veces y promedia.

**¿Cómo comparo el mismo prompt con dos modelos diferentes?**  
Usa `compare` con `--model-a` y `--model-b` apuntando al mismo YAML:
```bash
python -m promptkit.cli compare \
  prompts/mi_prompt.yaml \
  prompts/mi_prompt.yaml \
  --file inputs/mis_entradas.json \
  --model-a claude-haiku-4-5-20251001 \
  --model-b claude-sonnet-4-6
```

**El comando pide el texto pero solo aparece `>` sin mostrar lo que escribo.**  
Eso es normal en algunas terminales de Windows. El texto sí se está capturando. Escribe tu texto y presiona Enter (línea vacía para enviar en modo multilínea).

**¿Cómo agrego más créditos a mi cuenta de Anthropic?**  
Ve a [console.anthropic.com](https://console.anthropic.com) → Billing → Add credits.

---

*PromptKit — construido por [Ricardo](https://github.com/ricardomb-tech)*
