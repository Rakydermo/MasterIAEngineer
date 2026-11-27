# Spec Delta

## Purpose

Permite que el servicio invoque a cualquier proveedor de LLM bajo un nombre lógico de modelo, con failover ordenado, tiempo acotado, concurrencia limitada y errores normalizados, sin que el código de negocio sepa qué proveedor responde.

## ADDED Requirements

### Requirement: Invocación por nombre lógico de modelo

El servicio DEBE (MUST) invocar al proveedor LLM usando un nombre lógico de modelo definido en configuración. El código de negocio DEBE (MUST NOT) seleccionar el proveedor ni construir clientes por petición, y el cambio de proveedor DEBE (MUST) resolverse únicamente por configuración.

#### Scenario: Resolución del nombre lógico

- **WHEN** el servicio necesita una completación y la configuración define el nombre lógico con un despliegue concreto
- **THEN** la llamada se resuelve contra ese despliegue sin que el código de negocio mencione proveedor ni modelo físico

#### Scenario: Cambio de proveedor por configuración

- **WHEN** se cambia el despliegue asociado al nombre lógico en la configuración y se reinicia el servicio
- **THEN** la siguiente petición se atiende con el nuevo despliegue sin modificar código

#### Scenario: Reutilización de la conexión

- **WHEN** llegan varias peticiones consecutivas
- **THEN** el servicio reutiliza la misma instancia de cliente en lugar de crear una por petición

### Requirement: Failover ordenado entre despliegues

El servicio DEBE (MUST) intentar los despliegues configurados en orden de prioridad y DEBE (MUST) pasar al siguiente cuando el anterior falle. Si todos los despliegues fallan, DEBE (MUST) devolver el error normalizado del último intento. Un error de configuración o de credenciales DEBE (MUST NOT) considerarse recuperable por un despliegue posterior con la misma credencial inválida.

#### Scenario: Despliegue primario no disponible

- **WHEN** el despliegue primario falla y hay un despliegue secundario configurado y sano
- **THEN** la petición responde con éxito usando el secundario y la respuesta identifica al proveedor que respondió

#### Scenario: Todos los despliegues fallan

- **WHEN** el primario y el secundario fallan
- **THEN** la petición responde con el error normalizado del último intento, sin reintentos ilimitados

#### Scenario: Sin despliegue secundario

- **WHEN** no hay despliegue secundario configurado y el primario falla
- **THEN** la petición responde con el error normalizado del primario

### Requirement: Presupuesto de tiempo acotado

El servicio DEBE (MUST) aplicar un tiempo máximo configurable a cada intento de llamada al proveedor. El tiempo total de una petición DEBE (MUST) estar acotado por el número de intentos configurados multiplicado por ese tiempo máximo, más el backoff aplicado.

#### Scenario: Proveedor lento

- **WHEN** el proveedor no responde dentro del tiempo máximo por intento
- **THEN** el intento se aborta y la petición termina en un tiempo acotado, sin esperas indefinidas

#### Scenario: Tiempo total acotado

- **WHEN** se agotan todos los despliegues por tiempo de espera
- **THEN** el tiempo total de la petición no supera el presupuesto declarado por la configuración

### Requirement: Clasificación normalizada de fallos

El servicio DEBE (MUST) clasificar cualquier fallo del proveedor en una de estas categorías: tiempo agotado, saturación, fallo del proveedor, configuración o credenciales, y capacidad local agotada. La clasificación DEBE (MUST) ser independiente del proveedor que haya fallado.

#### Scenario: Tiempo agotado

- **WHEN** el proveedor no responde dentro del tiempo máximo
- **THEN** el fallo se clasifica como tiempo agotado

#### Scenario: Saturación del proveedor

- **WHEN** el proveedor responde con un límite de tasa
- **THEN** el fallo se clasifica como saturación

#### Scenario: Fallo del proveedor

- **WHEN** el proveedor responde con un error de servidor o falla la conexión
- **THEN** el fallo se clasifica como fallo del proveedor

#### Scenario: Credenciales o configuración inválidas

- **WHEN** el proveedor rechaza las credenciales o la petición construida es inválida
- **THEN** el fallo se clasifica como configuración o credenciales

#### Scenario: Fallo no reconocido

- **WHEN** el proveedor devuelve un error que no encaja en ninguna categoría conocida
- **THEN** el fallo se clasifica como fallo del proveedor y se registra el error original en el log

### Requirement: Concurrencia acotada con rechazo inmediato

El servicio DEBE (MUST) limitar el número de llamadas simultáneas al proveedor. Al alcanzar el límite, DEBE (MUST) rechazar la petición de inmediato, sin invocar al proveedor y sin mantenerla en espera, y DEBE (MUST) liberar el hueco al terminar la llamada, haya éxito o fallo.

#### Scenario: Capacidad disponible

- **WHEN** el número de llamadas en curso está por debajo del límite configurado
- **THEN** la petición se atiende con normalidad

#### Scenario: Capacidad agotada

- **WHEN** el número de llamadas en curso alcanza el límite configurado
- **THEN** la petición se rechaza de inmediato y el proveedor no recibe la llamada

#### Scenario: Liberación tras fallo

- **WHEN** una llamada que ocupaba un hueco termina con error
- **THEN** el hueco queda disponible para la siguiente petición

### Requirement: Respuesta normalizada del proveedor

Toda respuesta exitosa DEBE (MUST) exponer la estimación generada, el modelo físico que respondió, el proveedor que respondió y el consumo de tokens de entrada, salida y total, con independencia del proveedor utilizado.

#### Scenario: Respuesta del despliegue primario

- **WHEN** responde el despliegue primario
- **THEN** la respuesta identifica el modelo y el proveedor del primario

#### Scenario: Respuesta del despliegue secundario

- **WHEN** responde el despliegue secundario tras un fallo del primario
- **THEN** la respuesta identifica el modelo y el proveedor del secundario, no los del primario

### Requirement: Registro de consumo y coste

El servicio DEBE (MUST) registrar en el log, por cada llamada, el proveedor, el modelo, los tokens de entrada y salida y el coste estimado. El servicio DEBE (MUST NOT) reutilizar respuestas anteriores: dos peticiones idénticas DEBEN (MUST) invocar al proveedor dos veces.

#### Scenario: Registro de consumo

- **WHEN** una llamada al proveedor termina con éxito
- **THEN** el log incluye proveedor, modelo, tokens de entrada, tokens de salida y coste estimado de esa llamada

#### Scenario: Sin cache de respuestas

- **WHEN** se envían dos peticiones idénticas
- **THEN** el proveedor recibe dos llamadas y no se devuelve una respuesta almacenada

### Requirement: Validación de configuración al arranque

El servicio DEBE (MUST) impedir el arranque si el modelo configurado no incluye el proveedor, si falta la clave del proveedor de algún despliegue configurado o si algún tiempo máximo, número de reintentos o límite de concurrencia no es válido.

#### Scenario: Modelo sin proveedor

- **WHEN** el modelo configurado no incluye el prefijo de proveedor
- **THEN** el arranque falla con un error de configuración explícito

#### Scenario: Falta la clave del despliegue secundario

- **WHEN** hay un despliegue secundario configurado y falta su clave de API
- **THEN** el arranque falla con un error de configuración explícito

#### Scenario: Valor de configuración inválido

- **WHEN** un tiempo máximo, el número de reintentos o el límite de concurrencia tiene un valor negativo o cero donde no corresponde
- **THEN** el arranque falla con un error de configuración explícito
