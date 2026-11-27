# Spec Delta

## Purpose

Expone una API HTTP que recibe la transcripción de una reunión y devuelve una estimación de software generada por un LLM, sin persistir datos ni recuperar contexto externo (arquitectura CAG).

## ADDED Requirements

### Requirement: Health check

El servicio DEBE (MUST) exponer `GET /health` y responder 200 con el estado, la versión y el entorno de la aplicación.

#### Scenario: Servicio operativo

- **WHEN** se solicita `GET /health`
- **THEN** responde 200 con `status: "healthy"`, `version` y `environment`

### Requirement: Estimación desde transcripción

El servicio DEBE (MUST) aceptar `POST /api/v1/estimate` con un cuerpo JSON `{"transcription": "..."}` y devolver la estimación en markdown junto con el modelo, el proveedor y el uso de tokens.

#### Scenario: Transcripción válida

- **WHEN** se envía una transcripción de al menos 50 caracteres
- **THEN** responde 200 con `estimation`, `model`, `provider` y `usage` (tokens de entrada, salida y total)

#### Scenario: Transcripción inválida

- **WHEN** falta la transcripción o tiene menos de 50 caracteres
- **THEN** responde 422 y no se llama al proveedor LLM

### Requirement: Selección de proveedor

El servicio DEBE (MUST) seleccionar el proveedor LLM según `LLM_PROVIDER`, admitiendo `openai` y `anthropic`, y DEBE usar el modelo indicado en `LLM_MODEL`.

#### Scenario: Proveedor Anthropic

- **WHEN** `LLM_PROVIDER=anthropic` y existe `ANTHROPIC_API_KEY`
- **THEN** la estimación se solicita a Anthropic usando `LLM_MODEL`

#### Scenario: Proveedor OpenAI

- **WHEN** `LLM_PROVIDER=openai` y existe `OPENAI_API_KEY`
- **THEN** la estimación se solicita a OpenAI usando `LLM_MODEL`

#### Scenario: Proveedor no soportado

- **WHEN** `LLM_PROVIDER` no es `openai` ni `anthropic`
- **THEN** la aplicación no arranca y reporta un error de configuración

### Requirement: Validación de configuración al arrancar

El servicio DEBE (MUST) validar al arrancar que existe la API key del proveedor seleccionado y DEBE fallar con un mensaje claro si falta.

#### Scenario: Falta la clave del proveedor

- **WHEN** `LLM_PROVIDER=anthropic` y `ANTHROPIC_API_KEY` está vacía
- **THEN** el arranque falla indicando que `ANTHROPIC_API_KEY` es obligatoria

### Requirement: Error controlado del LLM

Si la llamada al proveedor LLM falla, el servicio DEBE (MUST) responder 500 con un mensaje de error descriptivo y DEBE registrar el fallo sin exponer secretos.

#### Scenario: Fallo del proveedor

- **WHEN** el proveedor devuelve un error o no responde
- **THEN** responde 500 con un `detail` descriptivo y registra el error con proveedor y modelo

### Requirement: Sin persistencia ni retrieval (CAG)

El servicio DEBE (MUST) ser stateless: no DEBE guardar transcripciones, estimaciones ni historial, y no DEBE consultar fuentes externas. El contexto DEBE limitarse a los ejemplos estáticos incluidos en el prompt.

#### Scenario: Peticiones independientes

- **WHEN** se envían dos estimaciones distintas
- **THEN** la segunda no depende de la primera y no se escribe ningún dato en disco ni en base de datos
