# Spec Delta

## MODIFIED Requirements

### Requirement: Estimación desde transcripción

El servicio DEBE (MUST) aceptar `POST /api/v1/estimate` con un cuerpo JSON `{"transcription": "..."}`, donde la transcripción tenga entre 50 y 50.000 caracteres y contenga al menos un carácter no blanco, y DEBE devolver la estimación en markdown junto con el modelo, el proveedor, el uso de tokens y el coste estimado en USD.

#### Scenario: Transcripción válida

- **WHEN** se envía una transcripción de entre 50 y 50.000 caracteres con contenido real
- **THEN** responde 200 con `estimation`, `model`, `provider` y `usage` (tokens de entrada, salida, total y `cost_usd`)

#### Scenario: Coste no disponible

- **WHEN** el modelo que responde no está en la tabla de precios de LiteLLM
- **THEN** responde 200 igualmente y `usage.cost_usd` vale `null`, sin hacer fallar la petición

#### Scenario: Transcripción inválida

- **WHEN** falta la transcripción, tiene menos de 50 caracteres o está formada solo por espacios en blanco
- **THEN** responde 422 y no se llama al proveedor LLM

#### Scenario: Transcripción demasiado larga

- **WHEN** la transcripción supera los 50.000 caracteres
- **THEN** responde 422 indicando el límite y no se llama al proveedor LLM

### Requirement: Error controlado del LLM

Si la llamada al proveedor LLM falla, el servicio DEBE (MUST) responder con un código que distinga la causa, con un mensaje estable que no exponga el mensaje original del proveedor, secretos ni detalles de la petición, y DEBE registrar el fallo completo con proveedor y modelo. La respuesta DEBE (MUST) incluir el identificador de petición para poder cruzar el error con el log.

#### Scenario: Tiempo de espera agotado

- **WHEN** el proveedor no responde dentro del presupuesto de tiempo configurado
- **THEN** responde 504 con un mensaje genérico y registra el timeout con proveedor y modelo

#### Scenario: Proveedor saturado

- **WHEN** el proveedor responde 429 tras agotar los intentos permitidos
- **THEN** responde 503 con la cabecera `Retry-After` y registra la saturación

#### Scenario: Fallo del proveedor

- **WHEN** el proveedor responde 5xx o falla la conexión tras agotar los intentos permitidos
- **THEN** responde 502 con un mensaje genérico y registra el error

#### Scenario: Error de configuración o credenciales

- **WHEN** el proveedor rechaza las credenciales o la configuración es inválida
- **THEN** responde 500 con un mensaje genérico y registra el error completo sin exponer la clave

#### Scenario: Sin filtración del mensaje del proveedor

- **WHEN** se produce cualquier fallo del proveedor
- **THEN** el campo `detail` de la respuesta no contiene el texto original del proveedor, identificadores de organización ni fragmentos de la petición

## REMOVED Requirements

### Requirement: Selección de proveedor

**Reason**: El proveedor deja de seleccionarse con `LLM_PROVIDER`. Se deriva del prefijo del modelo configurado y la resolución, incluido el failover, pasa a la capability `llm-abstraction`.

**Migration**: Configurar `LLM_MODEL` con prefijo (`anthropic/...`, `openai/...`) y, opcionalmente, `LLM_FALLBACK_MODEL`. Eliminar `LLM_PROVIDER` del entorno.

### Requirement: Validación de configuración al arrancar

**Reason**: La validación de claves y valores se redefine por despliegue en la capability `llm-abstraction`.

**Migration**: Mismo comportamiento; las claves se validan para cada modelo configurado en lugar de para el proveedor seleccionado.

## ADDED Requirements

### Requirement: Identificador de petición

Toda respuesta HTTP del servicio DEBE (MUST) incluir la cabecera `X-Request-ID` con un identificador generado por el servicio, y el mismo valor DEBE (MUST) aparecer en todas las líneas de log de esa petición. El servicio DEBE (MUST NOT) reutilizar un identificador enviado por el cliente.

#### Scenario: Petición sin identificador

- **WHEN** se envía una petición sin la cabecera `X-Request-ID`
- **THEN** la respuesta incluye un `X-Request-ID` no vacío y los logs de la petición usan ese mismo valor

#### Scenario: Identificador enviado por el cliente

- **WHEN** el cliente envía un `X-Request-ID`
- **THEN** el servicio genera uno nuevo y no reutiliza el valor recibido

#### Scenario: Respuesta de error controlado

- **WHEN** la petición termina con un error controlado del LLM
- **THEN** la respuesta incluye `X-Request-ID` y el log del error usa el mismo valor
