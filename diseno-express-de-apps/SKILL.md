---
name: diseno-express-de-apps
description: Diseña y construye una aplicación web en días copiando conceptos ya probados en el mercado — toma una plataforma referente (p. ej. Trello, Airbnb, Shopify), la disecciona desde información pública, decide qué copiar, qué adaptar y qué descartar, y la convierte en un proyecto propio con documentos de diseño (decisiones, análisis del referente, diseño visual, documento conceptual, casos de uso por etapas) y luego en código con Next.js + Supabase + Vercel, pensado para personas con poco conocimiento de desarrollo. Úsala cuando alguien diga "quiero crear una app/plataforma como X", "hagamos algo tipo Uber/Notion/Airbnb para…", "diseña una plataforma para…", "convierte esta idea en una app", "documento conceptual y casos de uso", "quiero lanzar un MVP rápido", "clonar el modelo de negocio de…", o pida pasar de una idea de negocio a una aplicación funcionando, aunque no mencione el stack ni la palabra skill.
---

# Diseño express de apps (copiar conceptos probados → app propia)

Filosofía: **no se inventa desde cero lo que el mercado ya validó**. Se elige
un referente que ya resolvió el problema, se disecciona su concepto, su
diseño y su modelo de negocio, y se aplica de forma agresiva a un proyecto
nuevo. Claude Code hace el trabajo técnico; la persona toma las decisiones.

Se copia el **concepto** (problema, flujos, modelo de datos, modelo de
negocio, patrones de interfaz). **Nunca** la marca, el logo, los textos, las
imágenes ni el código del referente. Ver §7.

`SKILL_DIR` = carpeta de este archivo. El script vive en `SKILL_DIR/scripts/expres.py`
(Python 3, sin dependencias).

## Reglas fijas (no se preguntan)

- **Stack**: Next.js (App Router, TypeScript, Tailwind, shadcn/ui) +
  **Supabase** (Postgres, Auth, RLS, Storage, Realtime) + **Vercel**
  (despliegue) + GitHub. No propongas otro framework, base de datos ni
  hosting aunque el referente use otros. Pagos, correo o IA se integran como
  servicios dentro de este stack (ver [references/construccion.md](references/construccion.md)).
- **Documentos en Markdown** en `docs/` del proyecto: son la fuente de
  verdad que Claude Code lee en cada sesión.
- **Usuario no técnico**: tú ejecutas los comandos, explicas en lenguaje
  llano qué hiciste y por qué, y solo le pides lo que solo él puede hacer
  (crear cuentas, iniciar sesión en Vercel/Supabase/GitHub, aprobar).
- **Velocidad sobre perfección**: propone siempre una opción recomendada;
  nunca dejes al usuario frente a una página en blanco.

## 0. Preparar (una vez por proyecto)

```bash
python3 SKILL_DIR/scripts/expres.py entorno
python3 SKILL_DIR/scripts/expres.py iniciar --proyecto RUTA --nombre "Nombre del proyecto"
```

`entorno` revisa Node ≥ 20, git, gh, Vercel CLI y Supabase CLI y dice cómo
instalar lo que falte (instálalo tú solo si el usuario acepta; sin `sudo`).
`iniciar` crea `RUTA/docs/` con las 6 plantillas y un `CLAUDE.md` del
proyecto; no sobrescribe nada que ya exista.

Si el proyecto **ya tiene una plataforma** construida, léela antes de
decidir: la especificación deberá decir qué se reutiliza y qué se construye
(ver [references/especificacion-propia.md](references/especificacion-propia.md#si-ya-existe-una-plataforma)).

## 1. Las cinco decisiones (compuertas) → `docs/00-decisiones.md`

Son el corazón del método. Detalle, preguntas guía y patrones en
[references/decisiones.md](references/decisiones.md).

| # | Decisión | Pregunta | Salida |
|---|---|---|---|
| D1 | Qué quiero construir | ¿Qué problema, para quién, con qué resultado medible? | Enunciado de una frase + usuarios + resultado |
| D2 | Basado en qué | ¿Qué plataforma(s) ya resolvieron esto? | 1 referente principal + 0-2 secundarios, con lo que se toma de cada uno |
| D3 | Qué diseño visual | ¿Cómo debe sentirse y verse? | Estilo, tono, densidad, plataforma (web/móvil) |
| D4 | Basado en qué | ¿Qué producto tiene esa estética? | Referente visual (puede ser distinto del funcional) |
| D5 | Qué modelo de negocio | ¿Cómo gana dinero (o valor) y quién paga? | Modelo copiado del referente y adaptado |

Cómo conducirlas:
1. Pide al usuario la idea en sus palabras. Con eso **propón tú** D1-D5
   completas, con 2-3 alternativas de referente y una recomendada.
2. Pregunta máximo 3 cosas a la vez (usa preguntas de opción múltiple si
   tu entorno las tiene). Si el usuario no sabe, decide tú y dilo.
3. Registra cada decisión con su **porqué** y marca `Estado: aprobada`
   solo cuando el usuario lo confirme. Sin D1-D5 aprobadas no se avanza.

## 2. Diseccionar el referente → `docs/01` y `docs/02`

Investiga el referente con información **pública** (sitio, precios, centro
de ayuda, portal de desarrolladores, reseñas). Usa búsqueda web y el
navegador si están disponibles. Produce:

- `01-referente-conceptual.md`: ficha, problema y propuesta de valor,
  **modelo de negocio** (cómo cobra, cuánto, ingresos complementarios),
  actores, dominios funcionales, objetos de datos y sus relaciones, ciclo de
  vida, capa de IA, diferenciadores, **limitaciones** y **lecturas
  aplicables** a nuestro proyecto.
- `02-referente-casos-de-uso.md`: catálogo `CU-MM-NN | caso | actor |
  resultado` por módulo, más integraciones que usa.

Cifras = "declaradas por la plataforma a <fecha>". Cita fuentes al final.
Guía completa en [references/analisis-referente.md](references/analisis-referente.md).
Si el usuario solo quiere avanzar rápido, un `02` de 40-60 casos basta; el
`01` no se salta.

## 3. Diseño visual → `docs/03-diseno-visual.md`

Del referente visual (D4) extrae **patrones**, no assets: estructura de
navegación, pantallas clave, densidad, jerarquía, componentes, estados
vacíos, tono de los textos. Tradúcelos a tokens propios (color, tipografía,
radios, espaciado) para Tailwind + shadcn/ui y a un inventario de pantallas.
Paleta y nombre propios: nada que confunda con la marca del referente.
Ver [references/diseno-visual.md](references/diseno-visual.md).

## 4. Especificación propia → `docs/04` y `docs/05`

Ver [references/especificacion-propia.md](references/especificacion-propia.md).

- `04-conceptual.md`: qué es (un párrafo), el **ciclo** que ordena la
  plataforma, roles, tabla **copiar / adaptar / descartar** frente al
  referente, módulos (M1…Mn) con funcionalidades, modelo de negocio,
  modelo de datos, arquitectura (stack fijo) y fases.
- `05-casos-de-uso.md`: casos por **etapas de construcción**:
  - `E0 Cimientos` siempre primero (identidad, roles, auditoría, despliegue).
  - `E1` = el **ciclo mínimo** que entrega valor real (el MVP).
  - Etapas siguientes: medir, monetizar, motivar, escalar…
  - Cada caso: `UC-MOD-nn`, actor, prioridad 🟥🟨🟩, puntos Fibonacci
    (1-13; si da 21, descomponer), estado ⬜/🔄/✅.
  - Cada etapa: propósito, duración estimada y **criterio de salida**
    verificable por el usuario.
  - Los casos 🟥 llevan ficha completa (precondición, disparador, flujo,
    alternativas, reglas de negocio, criterio de aceptación).

Valida antes de mostrar:

```bash
python3 SKILL_DIR/scripts/expres.py validar --proyecto RUTA
```

Corrige errores (IDs repetidos, puntos fuera de Fibonacci, etapas sin
criterio de salida, `TODO` sin resolver). **Compuerta**: presenta al usuario
un resumen de una pantalla (qué se construye en E0 y E1, cuánto tarda, qué
decide él) y espera su aprobación antes de escribir código.

## 5. Construcción por etapas

Guía técnica completa (comandos, estructura, Supabase, Vercel, pagos) en
[references/construccion.md](references/construccion.md). Resumen:

1. **E0 el primer día**: crear la app Next.js, repo en GitHub, proyecto en
   Supabase, conectar a Vercel y **desplegar** una página con login. El
   usuario ve una URL real desde el día uno.
2. **Modelo de datos** como migraciones SQL de Supabase (`supabase/migrations/`),
   con **RLS en todas las tablas** desde la primera migración.
3. **Bucle por etapa**: toma los casos de la etapa en orden de prioridad →
   implementa → prueba en local y en la URL de preview → marca 🔄/✅ en
   `05-casos-de-uso.md` → commit → despliegue.
4. **Cierre de etapa**: muestra al usuario el criterio de salida funcionando
   en la URL. Si lo acepta, corre una **auditoría rápida** con la skill
   [`auditoria-express-de-apps`](../auditoria-express-de-apps/SKILL.md)
   (completa antes de la primera salida a producción o de activar pagos) y
   resuelve sus 🟥 antes del merge a `main`; si no lo acepta, ajusta.
   Al empezar cada etapa, lee `docs/06-lecciones-aprendidas.md` si existe.
5. `python3 SKILL_DIR/scripts/expres.py estado --proyecto RUTA` muestra el
   avance por etapa en cualquier momento (útil al retomar una sesión).

Nunca: escribir secretos en el código ni en `docs/`; desactivar RLS "para
probar"; desplegar a producción sin que el usuario lo pida.

## 6. Reporte al usuario (al final de cada fase)

Breve y sin jerga: qué se decidió/construyó, la URL si existe, qué falta,
qué tiene que hacer él (si algo) y cuál es el siguiente paso recomendado.

## 7. Límites y cuidado legal

- Copiar ideas, flujos y modelos de negocio es legítimo; copiar **marca,
  textos, imágenes, diseño gráfico idéntico o código** no. Nombre, logo,
  paleta y textos son propios.
- No hagas scraping masivo ni uses APIs privadas del referente; solo
  información pública y su API documentada si la integración es real.
- Si el modelo maneja **dinero de terceros**, datos personales o datos
  sensibles, déjalo señalado en `04-conceptual.md` (protección de datos —
  p. ej. Ley 1581 en Colombia —, facturación electrónica, regulación de
  pagos) y recomienda usar una pasarela autorizada en vez de custodiar fondos.
- La IA dentro de la app propone; un humano aprueba lo que mueve dinero,
  reputación o decisiones.

Patrones que separan una especificación útil de una lista de deseos en
[references/lecciones-aprendidas.md](references/lecciones-aprendidas.md).
Léelos antes de escribir `04` y `05`.
