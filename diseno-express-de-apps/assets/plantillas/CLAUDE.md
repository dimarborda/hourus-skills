# {{PROYECTO}}

Aplicación diseñada con el método de diseño express (skill
`diseno-express-de-apps`). La persona dueña del proyecto puede no ser
desarrolladora: explica cada cambio en una frase sin jerga.

## Fuente de verdad

Los documentos de `docs/` mandan sobre cualquier suposición:

| Archivo | Contenido |
|---|---|
| `docs/00-decisiones.md` | Qué se construye, referentes, diseño y modelo de negocio |
| `docs/01-referente-conceptual.md` | Análisis del referente |
| `docs/02-referente-casos-de-uso.md` | Catálogo de casos del referente |
| `docs/03-diseno-visual.md` | Tokens, navegación e inventario de pantallas |
| `docs/04-conceptual.md` | Concepto, ciclo, módulos, modelo de datos, fases |
| `docs/05-casos-de-uso.md` | Backlog por etapas con estado ⬜/🔄/✅ |
| `docs/06-lecciones-aprendidas.md` | Reglas aprendidas de las auditorías (se crea con la primera) |
| `docs/auditoria/` | Informes de auditoría por fecha |

Al terminar un caso de uso, actualiza su estado en `docs/05-casos-de-uso.md`.

## Stack (fijo)

- Next.js App Router + TypeScript + Tailwind + shadcn/ui, en Vercel.
- Supabase: Postgres, Auth, Storage, Realtime. Clientes en `src/lib/supabase/`.
- Migraciones en `supabase/migrations/`; aplicar con `npx supabase db push`
  y regenerar tipos con `npx supabase gen types typescript --linked > src/lib/database.types.ts`.

## Reglas

- RLS activado en todas las tablas, en la misma migración que las crea.
- Nunca secretos en el código ni en `docs/`; la service role key solo en el servidor.
- `npm run build` sin errores antes de cada push.
- Trabajo en ramas `etapa-eN`; producción (`main`) solo con aprobación del dueño.
- Tablas en español, `snake_case`, plural.
- Antes de cada etapa, lee `docs/06-lecciones-aprendidas.md` (si existe) y cumple sus
  reglas. Al cerrar cada etapa, auditoría rápida con la skill `auditoria-express-de-apps`.
