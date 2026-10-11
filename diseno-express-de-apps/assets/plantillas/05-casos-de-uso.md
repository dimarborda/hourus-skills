# {{PROYECTO}} · Casos de uso por etapas

Versión 1 · {{FECHA}}

## Cómo leer este documento

- ID `UC-MOD-nn`; los IDs no se reutilizan.
- Prioridad: 🟥 alta (sin ella la etapa no cierra) · 🟨 media · 🟩 baja.
- Puntos Fibonacci: 1, 2, 3, 5, 8, 13. Nada supera 13.
- Estado: ⬜ pendiente · 🔄 en construcción · ✅ terminado y verificado.

## Prefijos

| Prefijo | Módulo | Etapa |
|---|---|---|
| FND | Cimientos: identidad, roles, auditoría | E0 |
| TODO | TODO | TODO |

## Actores

| Actor | Qué hace | Qué NO puede hacer |
|---|---|---|
| Sistema | Ejecuta procesos automáticos con reglas versionadas | Actuar sin una regla vigente ni sin dejar traza |
| TODO | TODO | TODO |

## Mapa de etapas

| Etapa | Propósito | Módulos | Duración | Criterio de salida |
|---|---|---|---|---|
| E0 | Cimientos | FND | TODO | Una persona entra, pertenece a su organización y toda acción sensible queda en bitácora |
| E1 | Operar el ciclo (MVP) | TODO | TODO | TODO |

## E0 · Cimientos

**Criterio de salida:** una persona entra, pertenece a su organización con un rol y toda acción sensible queda en bitácora; la app está publicada en una URL de Vercel.

| ID | Caso de uso | Actor | Prioridad | Puntos | Estado |
|---|---|---|---|---|---|
| UC-FND-01 | Crear cuenta e iniciar sesión | Visitante | 🟥 | 3 | ⬜ |
| UC-FND-02 | Completar el perfil | Usuario | 🟥 | 2 | ⬜ |
| UC-FND-03 | Crear organización e invitar miembros | Administrador | 🟥 | 5 | ⬜ |
| UC-FND-04 | Asignar y cambiar roles | Administrador | 🟥 | 3 | ⬜ |
| UC-FND-05 | Consultar la bitácora de auditoría | Administrador | 🟨 | 3 | ⬜ |

### UC-FND-01 · Crear cuenta e iniciar sesión
- **Actor:** Visitante
- **Precondición:** no existe una cuenta con el mismo correo.
- **Disparador:** el visitante elige registrarse o iniciar sesión.
- **Flujo principal:** 1) Ingresa su correo. 2) Recibe el enlace o código. 3) Confirma. 4) Se crea su perfil y entra al inicio.
- **Alternativas:** correo ya registrado → inicia sesión; enlace vencido → se reenvía.
- **Reglas de negocio:** el perfil se crea automáticamente al registrarse.
- **Criterio de aceptación:** una persona nueva entra con su correo desde la URL pública y ve su nombre en pantalla.

### UC-FND-02 · Completar el perfil
- **Actor:** Usuario
- **Precondición:** sesión iniciada.
- **Disparador:** primer ingreso o edición del perfil.
- **Flujo principal:** 1) Completa nombre y foto. 2) Guarda.
- **Alternativas:** foto demasiado grande → se rechaza con mensaje claro.
- **Reglas de negocio:** cada persona solo edita su propio perfil.
- **Criterio de aceptación:** el cambio se ve al recargar y otra persona no puede editarlo.

### UC-FND-03 · Crear organización e invitar miembros
- **Actor:** Administrador
- **Precondición:** sesión iniciada.
- **Disparador:** crea su organización o equipo.
- **Flujo principal:** 1) Registra la organización. 2) Invita por correo con un rol. 3) El invitado acepta y queda como miembro.
- **Alternativas:** invitación vencida o a otro correo → se rechaza.
- **Reglas de negocio:** los permisos salen del rol en cada organización, no de la persona.
- **Criterio de aceptación:** un miembro solo ve los datos de las organizaciones a las que pertenece.

### UC-FND-04 · Asignar y cambiar roles
- **Actor:** Administrador
- **Precondición:** organización activa.
- **Disparador:** cambio de responsabilidades.
- **Flujo principal:** 1) Consulta miembros. 2) Asigna rol. 3) Confirma. 4) Queda en bitácora.
- **Alternativas:** quitar al último administrador → se impide.
- **Reglas de negocio:** todo cambio de rol registra quién, cuándo y por qué.
- **Criterio de aceptación:** el cambio aparece en la bitácora y los permisos cambian al instante.

## E1 · TODO

**Criterio de salida:** TODO — un usuario real completa el ciclo una vez, sin herramientas paralelas.

| ID | Caso de uso | Actor | Prioridad | Puntos | Estado |
|---|---|---|---|---|---|
| UC-TODO-01 | TODO | TODO | 🟥 | 3 | ⬜ |

## Reglas globales

| Código | Regla |
|---|---|
| RG-01 | Todo cambio de estado registra actor, fecha y motivo. |
| RG-02 | La IA propone; un humano aprueba lo que mueve dinero, reputación o decisiones. |
| TODO | TODO |

## Eventos y notificaciones

| Evento | Destinatario | Canal |
|---|---|---|
| Invitación o cambio de rol | Usuario afectado | Aplicación y correo |
| TODO | TODO | TODO |

## Decisiones pendientes del usuario

- TODO
