# Especificación del proyecto propio

Dos documentos: el **conceptual** del proyecto (`04`) y sus **casos de uso
por etapas de construcción** (`05`), que es el backlog que Claude Code
ejecuta. Si el proyecto ya tiene plataforma, ver la última sección.

## `04-conceptual.md`

1. **Qué es** — un párrafo: qué hace, para quién y su **rasgo distintivo**
   (p. ej. en un gestor de tareas: "ninguna tarea nace
   suelta, todas salen de un objetivo del plan estratégico").
2. **El ciclo que ordena la plataforma** — 4-7 pasos numerados que vuelven
   a empezar. Si no hay ciclo claro, D1 está mal definido.
3. **Roles** — `rol | responsabilidad`. Aclara si una persona puede tener
   roles distintos en contextos distintos (los permisos salen del rol en
   cada contexto, no de la persona).
4. **Copiar / adaptar / descartar** — tabla frente al referente. Es lo que
   hace explícito el método:

   | Del referente | Decisión | Cómo queda aquí |
   |---|---|---|
   | Red de afiliados | Descartar en MVP | Etapa 5 |
   | Transacción como objeto central | Copiar | Tabla `transacciones`, su estado gobierna el acceso |

5. **Módulos** — `M1…Mn`, cada uno con una frase de propósito y 3-6
   funcionalidades concretas.
6. **Modelo de negocio** — desde D5: quién paga, cuánto, cuándo, qué entra
   al MVP.
7. **Modelo de datos** — entidades principales, atributos clave y
   relaciones. Nombres de tablas en español y `snake_case` plural.
8. **Arquitectura** — fija:

   | Capa | Solución |
   |---|---|
   | Frontend | Next.js (App Router, TypeScript, Tailwind, shadcn/ui) en Vercel |
   | Datos | Supabase: Postgres, Auth, RLS por rol, Storage, Realtime |
   | Repositorio | GitHub; preview por rama, producción desde `main` |
   | Automatización | Vercel Cron / Supabase Edge Functions (o n8n si ya existe) |
   | IA (si aplica) | AI SDK vía API de Claude u otro proveedor, siempre con aprobación humana |
   | Pagos (si aplica) | Pasarela autorizada (Stripe, Mercado Pago, Wompi…) con webhooks → Supabase |

9. **Fases** — `fase | alcance | módulos | duración`, con la justificación
   del orden (p. ej. "incentivos al final: primero se estabiliza la medición").
10. **Cumplimiento** — datos personales, dinero de terceros, facturación.

## `05-casos-de-uso.md`

### Convenciones

- **ID**: `UC-MOD-nn`, `MOD` = prefijo de 3 letras del módulo (`FND`,
  `KBN`…). Los IDs no se reutilizan: un caso descartado deja su número
  vacante.
- **Prioridad**: 🟥 alta (sin ella la etapa no cierra), 🟨 media (tolera
  esperar una etapa), 🟩 baja (mejora).
- **Puntos**: Fibonacci 1, 2, 3, 5, 8, 13. Nada supera 13; lo que llegaría
  a 21 se descompone antes de escribirlo.
- **Estado**: ⬜ pendiente, 🔄 en construcción, ✅ terminado y verificado.
- Tabla de prefijos `prefijo | módulo | etapa`.
- Tabla de actores `actor | qué hace | qué NO puede hacer` (la columna
  "no puede" evita permisos excesivos y se traduce directo a RLS). El
  sistema / motor de reglas y la IA son actores con permisos propios.

### Etapas

- **E0 Cimientos** (siempre): cuenta e inicio de sesión, perfiles y roles,
  catálogos básicos, bitácora de auditoría, despliegue. Criterio de salida
  típico: "una persona entra, pertenece a un equipo/organización y toda
  acción sensible queda en bitácora".
- **E1 Operar el ciclo**: el mínimo para que un usuario real complete el
  ciclo de `04` una vez, sin hojas de cálculo paralelas. Es el MVP.
- **E2…En**: medir y alertar → reportar → monetizar → motivar → escalar
  (multiempresa / SaaS). Lo que mueve dinero o reputación va después de
  que la medición es confiable.
- Tabla del mapa de etapas: `etapa | propósito | módulos | casos | duración
  | criterio de salida`.

Cada etapa en el documento es un encabezado `## E<n> · <nombre>` seguido de
`**Criterio de salida:** …`, la tabla de casos y las fichas de los casos 🟥.

### Tabla de casos (formato que lee `expres.py`)

```
| ID | Caso de uso | Actor | Prioridad | Puntos | Estado |
|---|---|---|---|---|---|
| UC-FND-01 | Crear cuenta e iniciar sesión | Visitante | 🟥 | 3 | ⬜ |
```

### Ficha de un caso 🟥

```
### UC-FND-01 · Crear cuenta e iniciar sesión
- **Actor:** …
- **Precondición:** …
- **Disparador:** …
- **Flujo principal:** 1) … 2) … 3) …
- **Alternativas:** …
- **Reglas de negocio:** …
- **Criterio de aceptación:** … (verificable con sí/no)
```

Reglas de negocio que casi siempre hacen falta: valores calculados nunca se
digitan a mano (se muestra la fórmula); lo aprobado queda sellado con
fecha y persona; cambios de estado registran actor, fecha y motivo; la IA
redacta pero no aprueba; operaciones financieras se corrigen con ajustes,
nunca borrando.

### Al final del documento

- **Reglas globales** (`RG-01…`) y **criterios globales de aceptación**.
- **Eventos y notificaciones**: `evento | destinatario | canal`.
- **Decisiones pendientes** del usuario.

## Si ya existe una plataforma

Antes de los casos, agrega:

1. **Por qué no es lo que la plataforma ya tiene**: distingue conceptos con
   nombres parecidos y explica qué se rompe si se mezclan.
2. Casos nuevos numerados **a continuación** de los existentes.
3. **Qué se reutiliza y qué hay que construir**: `pieza | ya existe / por
   construir | observación`. Extender lo existente antes que duplicarlo.
4. **Lo que hay que decidir antes**: decisiones que no debe tomar la plataforma.
