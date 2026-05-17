# PromptKit

> **Toolkit de ingeniería de prompts para la línea de comandos.**  
> Diseña, prueba, compara y mejora tus prompts de IA — con Claude o con modelos locales gratuitos como Ollama.

---

## ¿Qué problema resuelve?

Cuando trabajas con IA generativa, el mayor desafío no es el modelo — es el **prompt**. Un prompt mal escrito da respuestas inconsistentes, costosas y difíciles de evaluar. PromptKit resuelve eso:

| Sin PromptKit | Con PromptKit |
|---------------|---------------|
| Pegas texto en ChatGPT y esperas | Defines el prompt una vez en un archivo YAML |
| No sabes si el prompt es bueno o malo | Cada respuesta recibe un puntaje de calidad automático (0.0 – 1.0) |
| Pruebas de una en una a mano | Procesas 5, 50 o 500 textos con un solo comando |
| No sabes cuál versión del prompt es mejor | Comparas dos prompts lado a lado con veredicto automático |
| Pierdes el historial de lo que funcionó | Todos los resultados se guardan por fecha automáticamente |
| Pagas por cada prueba en la nube | Corre gratis y offline con Ollama + llama3.2 |

**En una frase:** PromptKit convierte la ingeniería de prompts de un arte informal en un proceso medible y repetible.

---

## ¿Para quién es?

- Desarrolladores que integran IA en sus productos
- Analistas que quieren procesar texto en volumen (emails, tickets, reseñas)
- Cualquier persona que quiera experimentar con IA **sin pagar por cada prueba**
- Equipos que necesitan comparar modelos y versiones de prompts

---

## Índice

1. [Instalación](#1-instalación)
2. [Configuración — elige tu provider](#2-configuración--elige-tu-provider)
   - [Opción A: Anthropic Claude (nube)](#opción-a-anthropic-claude-nube)
   - [Opción B: Ollama (local y gratis)](#opción-b-ollama-local-y-gratis)
3. [Estructura del proyecto](#3-estructura-del-proyecto)
4. [Formato del archivo YAML de prompt](#4-formato-del-archivo-yaml-de-prompt)
5. [Comandos](#5-comandos)
   - [run — una sola vez](#51-run--una-sola-vez)
   - [chat — loop interactivo](#52-chat--loop-interactivo)
   - [batch — múltiples entradas](#53-batch--múltiples-entradas)
   - [compare — A/B test](#54-compare--ab-test)
   - [history — historial de calidad](#55-history--historial-de-calidad)
   - [new — crear prompt nuevo](#56-new--crear-prompt-nuevo)
6. [Modelos disponibles](#6-modelos-disponibles)
7. [Cómo se mide la calidad](#7-cómo-se-mide-la-calidad)
8. [Dónde se guardan los resultados](#8-dónde-se-guardan-los-resultados)
9. [Modo mock](#9-modo-mock)
10. [Prompts de ejemplo incluidos](#10-prompts-de-ejemplo-incluidos)
11. [Qué texto poner como entrada](#11-qué-texto-poner-como-entrada)
12. [Preguntas frecuentes](#12-preguntas-frecuentes)

---

## 1. Instalación

Requiere **Python 3.10+**.

```bash
cd PromptKit
pip install -e .
```

---

## 2. Configuración — elige tu provider

PromptKit soporta dos providers. Puedes usar uno, el otro, o ambos al mismo tiempo.

---

### Opción A: Anthropic Claude (nube)

**Costo:** paga por token | **Calidad:** muy alta | **Requiere:** internet + API key

1. Crea tu cuenta en [console.anthropic.com](https://console.anthropic.com)
2. Obtén tu API key
3. Crea el archivo `.env` en la raíz del proyecto:

```
ANTHROPIC_API_KEY=sk-ant-api03-TU-CLAVE-AQUI
```

Uso:
```bash
python -m promptkit.cli chat prompts/example_classifier.yaml --provider anthropic
```

---

### Opción B: Ollama (local y gratis)

**Costo:** $0.00 siempre | **Calidad:** buena | **Requiere:** instalar Ollama

#### Instalar Ollama

1. Descarga el instalador: **[ollama.com/download/OllamaSetup.exe](https://ollama.com/download/OllamaSetup.exe)**
2. Instala normalmente

> **Nota Windows 11:** Si aparece "Control Inteligente de Aplicaciones bloqueó esta app", ve a:  
> Configuración → Privacidad y seguridad → Seguridad de Windows → Control de aplicaciones y navegador → **Desactivar Smart App Control**

#### Descargar un modelo

Abre una terminal nueva después de instalar Ollama y ejecuta:

```bash
# Recomendado para 8 GB RAM + GPU dedicada
ollama pull llama3.2

# Alternativas
ollama pull mistral       # mejor en JSON (requiere 6 GB VRAM libre)
ollama pull qwen2.5       # excelente en instrucciones
```

#### Verificar que funciona

```bash
ollama list               # muestra modelos instalados
ollama run llama3.2 "di solo: funciona"
```

Uso con PromptKit:
```bash
python -m promptkit.cli chat prompts/example_ollama.yaml --provider ollama --model llama3.2
```

#### Comparación de providers

| | Anthropic (Claude) | Ollama (local) |
|--|--|--|
| **Costo** | Paga por token | **$0.00 siempre** |
| **Calidad** | Muy alta | Buena |
| **Velocidad** | Rápido (nube) | Depende de tu PC |
| **Privacidad** | Datos van a la nube | **Todo en tu máquina** |
| **Internet** | Requerido | **No necesita** |
| **GPU** | No aplica | RTX 3050+ recomendado |

---

## 3. Estructura del proyecto

```
PromptKit/
│
├── prompts/                        ← Tus archivos de prompt (.yaml)
│   ├── example_classifier.yaml     ← Clasifica texto en categorías
│   ├── example_extractor.yaml      ← Extrae datos estructurados
│   └── example_ollama.yaml         ← Optimizado para modelos locales
│
├── inputs/                         ← Archivos de entrada para batch/compare
│   └── example_inputs.json         ← 5 casos de prueba de ejemplo
│
├── results/                        ← Se crea automáticamente
│   └── 2026-05-17/
│       └── example_classifier.json
│
├── promptkit/
│   ├── evaluator.py                ← Motor principal (Anthropic + Ollama)
│   ├── storage.py                  ← Guardar y leer resultados
│   └── cli.py                      ← Todos los comandos
│
├── .env                            ← Tu API key de Anthropic (no subir a Git)
├── .env.example                    ← Plantilla de configuración
├── requirements.txt
└── setup.py
```

---

## 4. Formato del archivo YAML de prompt

```yaml
version: "1.0"
name: mi_clasificador
description: Clasifica emails en categorías de soporte
model: llama3.2            # modelo por defecto
provider: ollama           # anthropic u ollama
max_tokens: 512

system_prompt: |
  Eres un experto en clasificación de texto.
  Responde ÚNICAMENTE con JSON válido.

user_template: |
  Clasifica el siguiente texto:

  Texto: {texto}

  Devuelve JSON:
  {
    "categoria": "...",
    "confianza": 0.0
  }

expected_output_fields:
  - categoria
  - confianza
```

### ¿Qué va en `{text}`?

Los `{nombre}` en el template son **variables** — texto que tú escribes cada vez que corres el prompt. Ejemplos:

| Variable | Qué escribir |
|----------|-------------|
| `{text}` | Cualquier mensaje, ticket, email, reseña, noticia |
| `{texto}` | Lo mismo en español |
| `{email}` | El contenido de un email |
| `{review}` | Una reseña de producto |

No hay respuesta incorrecta — escribe lo que quieras analizar y el modelo lo procesa.

---

## 5. Comandos

### 5.1 `run` — Una sola vez

```bash
# Modo interactivo — te pide el texto en la terminal
python -m promptkit.cli run prompts/example_classifier.yaml --provider ollama --model llama3.2

# Con Anthropic
python -m promptkit.cli run prompts/example_classifier.yaml --provider anthropic
```

**Opciones:**

| Opción | Descripción |
|--------|-------------|
| `--provider ollama` | Usa modelo local gratuito |
| `--provider anthropic` | Usa Claude en la nube |
| `--model llama3.2` | Modelo específico |
| `--ollama-url` | URL de Ollama (default: `http://localhost:11434`) |
| `--input-file ruta.json` | Lee entrada desde archivo |
| `--mock` | Sin llamar a ninguna API |
| `--no-save` | No guardar resultado |

---

### 5.2 `chat` — Loop interactivo

El comando más útil para uso diario. Escribes texto, ves el análisis, escribes otro, sin salir.

```bash
# Con Ollama (gratis)
python -m promptkit.cli chat prompts/example_classifier.yaml --provider ollama --model llama3.2

# Con Claude
python -m promptkit.cli chat prompts/example_classifier.yaml --provider anthropic --model claude-haiku-4-5-20251001
```

```
┌────────────────────────────────────────────────────────┐
│ Chat mode: example_classifier (llama3.2)  [ollama]     │
│ Variables: text                                        │
│ Escribe tus respuestas. Presiona Ctrl+C para salir.    │
└────────────────────────────────────────────────────────┘

──────────── Corrida #1 ────────────
  text  (escribe tu texto; línea vacía para terminar)
  > La app no carga desde esta mañana
  >
Quality: 0.88  |  JSON: ✓  |  Campos: ✓  |  Costo: $0.00

──────────── Corrida #2 ────────────
  text  (escribe tu texto; línea vacía para terminar)
  > _
```

**Ctrl+C** para salir.

---

### 5.3 `batch` — Múltiples entradas

Procesa una lista de textos de un archivo JSON de una sola vez.

```bash
python -m promptkit.cli batch prompts/example_classifier.yaml \
  --provider ollama --model llama3.2 \
  --file inputs/example_inputs.json
```

**Formato del archivo de entradas** (`inputs/example_inputs.json`):

```json
[
  { "text": "El servidor se cayó a las 3am" },
  { "text": "Me cobraron dos veces este mes" },
  { "text": "Quisiera una opción de modo oscuro" },
  { "text": "¿Tienen período de prueba gratuito?" },
  { "text": "Llevo 2 semanas esperando respuesta" }
]
```

Resultado — tabla resumen con calidad, latencia y costo por entrada.

---

### 5.4 `compare` — A/B test

Compara dos prompts con las mismas entradas y declara un ganador.

```bash
# Comparar dos prompts distintos
python -m promptkit.cli compare \
  prompts/example_classifier.yaml \
  prompts/example_extractor.yaml \
  --file inputs/example_inputs.json \
  --provider ollama --model llama3.2
```

```bash
# Comparar llama3.2 (gratis) vs Claude (nube)
python -m promptkit.cli compare \
  prompts/example_classifier.yaml \
  prompts/example_classifier.yaml \
  --file inputs/example_inputs.json \
  --provider-a ollama     --model-a llama3.2 \
  --provider-b anthropic  --model-b claude-haiku-4-5-20251001
```

**Salida:**
```
┌──────────────────────────── Verdict ─────────────────────────────┐
│ Winner: example_classifier                                        │
│ Puntaje mayor (0.921 vs 0.887). Calidad: 0.91 vs 0.87           │
└───────────────────────────────────────────────────────────────────┘
```

**Opciones:**

| Opción | Descripción |
|--------|-------------|
| `--provider` | Provider para ambos |
| `--provider-a` / `--provider-b` | Provider individual por prompt |
| `--model-a` / `--model-b` | Modelo individual por prompt |
| `--model` | Mismo modelo para ambos |

---

### 5.5 `history` — Historial de calidad

Muestra la evolución del puntaje de un prompt a lo largo del tiempo.

```bash
python -m promptkit.cli history example_classifier
```

```
        History — example_classifier
╭────────────┬───────────┬─────────┬──────┬──────────────╮
│ Date       │ Model     │ Quality │ JSON │ Latency (ms) │
├────────────┼───────────┼─────────┼──────┼──────────────┤
│ 2026-05-15 │ llama3.2  │   0.872 │  ✓   │          312 │
│ 2026-05-16 │ llama3.2  │   0.891 │  ✓   │          287 │
│ 2026-05-17 │ mistral   │   0.943 │  ✓   │          401 │
╰────────────┴───────────┴─────────┴──────┴──────────────╯

Trend: ↑ improving (+0.071)
```

---

### 5.6 `new` — Crear prompt nuevo

Crea un archivo YAML paso a paso desde la terminal.

```bash
python -m promptkit.cli new mi_analizador
```

Te pregunta: descripción, modelo, provider, system prompt, template, campos esperados.

---

## 6. Modelos disponibles

### Ollama (gratis, local)

| Modelo | RAM necesaria | Bueno para |
|--------|--------------|------------|
| `llama3.2` | 2 GB VRAM | Uso general, rápido — **recomendado para empezar** |
| `mistral` | 4 GB VRAM | JSON estructurado, instrucciones complejas |
| `qwen2.5` | 4 GB VRAM | Análisis de texto, multilingüe |
| `phi3.5` | 2 GB VRAM | Ultra ligero, respuestas cortas |

### Anthropic Claude (nube, de pago)

| Modelo | Precio entrada/salida | Bueno para |
|--------|-----------------------|------------|
| `claude-haiku-4-5-20251001` | $0.00000025 / $0.00000125 | Clasificación rápida y barata |
| `claude-sonnet-4-6` | $0.000003 / $0.000015 | Balance calidad/precio |
| `claude-opus-4-7` | $0.000015 / $0.000075 | Máxima calidad |

---

## 7. Cómo se mide la calidad

Cada respuesta recibe un **quality score** de 0.0 a 1.0. Lo calcula un modelo de IA que actúa como juez evaluando si la respuesta es correcta, completa y bien formateada.

| Puntaje | Significado |
|---------|-------------|
| 0.9 – 1.0 | Excelente |
| 0.7 – 0.89 | Bueno |
| 0.4 – 0.69 | Regular |
| 0.0 – 0.39 | Falla |

Además valida:
- **JSON válido** ✓/✗ — si la respuesta es parseable
- **Campos requeridos** ✓/✗ — si tiene todos los campos del YAML

> Con Ollama el juez usa el mismo modelo local. Con Anthropic usa Claude Haiku.

---

## 8. Dónde se guardan los resultados

```
results/
└── 2026-05-17/
    └── example_classifier.json   ← lista de todos los runs del día
```

Cada registro incluye: modelo, provider, latencia, tokens, costo, puntaje, input, output.

---

## 9. Modo mock

Todos los comandos aceptan `--mock` para probar sin llamar a ninguna API:

```bash
python -m promptkit.cli chat prompts/example_classifier.yaml --mock
python -m promptkit.cli compare prompts/example_classifier.yaml prompts/example_extractor.yaml --file inputs/example_inputs.json --mock
```

---

## 10. Prompts de ejemplo incluidos

### `example_classifier.yaml`
Clasifica cualquier texto en: `technical_issue`, `billing`, `feature_request`, `general_inquiry`, `complaint`.

**Pruébalo con:**
- `"La app no abre desde esta mañana"`
- `"Me cobraron dos veces en mi tarjeta"`
- `"Sería bueno tener modo oscuro"`

### `example_extractor.yaml`
Extrae entidades (personas, fechas, lugares), sentimiento, hechos clave y si requiere acción.

**Pruébalo con:**
- Cualquier email o mensaje
- Una noticia corta
- Un reporte de incidente

### `example_ollama.yaml`
Optimizado para modelos locales. Clasifica por categoría, sentimiento y urgencia.

**Pruébalo con:**
- `"Llevo 3 días sin poder entrar a mi cuenta"`
- `"Quiero cancelar mi plan"`
- `"Excelente servicio, muy satisfecho"`

---

## 11. Qué texto poner como entrada

Cuando el sistema pide `text`, escribe **cualquier texto que quieras analizar**:

```
Mensajes de soporte:
→ "La aplicación se cayó y perdí todo mi trabajo de hoy"
→ "Llevo esperando mi pedido 2 semanas y nadie responde"

Emails:
→ "Hola, necesito cancelar mi suscripción del plan Pro"

Reseñas:
→ "El producto llegó roto y el empaque estaba dañado"

Noticias:
→ "Apple anunció en San Francisco el lanzamiento del iPhone 17"

Lo que quieras:
→ Cualquier oración o párrafo en cualquier idioma
```

No hay texto incorrecto — el modelo analiza lo que sea que escribas.

---

## 12. Preguntas frecuentes

**¿Necesito internet para usar Ollama?**  
No. Una vez descargado el modelo, todo corre offline en tu PC.

**¿Cuánto cuesta usar Ollama?**  
Absolutamente $0.00. El modelo corre en tu hardware.

**¿En qué se diferencia llama3.2 de Claude?**  
Claude es más inteligente y preciso, especialmente en tareas complejas. llama3.2 es gratuito, privado y suficientemente bueno para clasificación y extracción básica.

**¿Puedo usar los dos providers al mismo tiempo?**  
Sí. El comando `compare` acepta `--provider-a ollama --provider-b anthropic` para comparar ambos directamente.

**¿Cómo creo mi propio prompt?**  
```bash
python -m promptkit.cli new nombre_del_prompt
```
Te guía paso a paso.

**Ollama dice "out of memory"**  
Cierra el navegador y otras apps, luego intenta de nuevo. Si persiste, usa `llama3.2` que solo necesita 2 GB de VRAM.

**¿Dónde veo los resultados guardados?**  
En la carpeta `results/YYYY-MM-DD/` del proyecto.

---

## Flujo de trabajo recomendado

```
1. Diseña tu prompt → promptkit new mi_prompt
2. Prueba manualmente → promptkit chat mi_prompt.yaml --provider ollama
3. Evalúa en volumen → promptkit batch mi_prompt.yaml --file mis_textos.json
4. Compara versiones → promptkit compare v1.yaml v2.yaml --file mis_textos.json
5. Rastrea mejoras → promptkit history mi_prompt
```

---

<<<<<<< Updated upstream
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
=======
*PromptKit — construido con [Claude API](https://anthropic.com), [Ollama](https://ollama.com) y [Rich](https://github.com/Textualize/rich)*
>>>>>>> Stashed changes
