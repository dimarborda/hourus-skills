# Equipo B · Despliegue (Vercel CLI y Supabase CLI)

Verifica que **lo publicado** coincide con lo que el repositorio dice y que
la configuración de los proveedores no abre puertas que el código cerró.
Requiere que el usuario haya iniciado sesión en ambos CLI y vinculado el
proyecto (`vercel link`, `npx supabase link --project-ref REF`). Si falta,
regístralo como hallazgo `info` y audita lo que se pueda.

## Comandos prohibidos durante la auditoría

Cambian estado o exponen valores. **No se ejecutan**, ni "para probar":

```
vercel env pull · vercel env add · vercel env rm · vercel deploy · vercel --prod
vercel promote · vercel rollback · vercel remove · vercel domains rm · vercel alias
supabase db push · supabase db reset · supabase migration repair · supabase secrets set
supabase functions deploy · supabase link (a otro proyecto) · cualquier SQL que no sea SELECT
```

Si un comando de lectura imprime un valor secreto, no lo copies: anota el
nombre y enmascara.

## B1 · Vercel

```bash
vercel whoami                     # equipo/cuenta: ¿es la del cliente o una personal?
vercel project ls                 # proyecto vinculado
cat .vercel/project.json          # projectId y orgId (no son secretos)
vercel ls                         # despliegues recientes, entorno y estado
vercel inspect <url-del-despliegue>   # build, región, funciones, alias
vercel env ls                     # NOMBRES y entornos (los valores salen cifrados)
vercel domains ls                 # dominios
vercel logs <url-del-despliegue>  # errores recientes (busca trazas con datos sensibles)
```

Verifica:

- [ ] **Variables**: ninguna `NEXT_PUBLIC_*` con nombre de secreto; la
      `service_role`/`sb_secret_` y llaves de pasarela/IA existen **solo**
      sin prefijo público. Preview y producción con valores **distintos**
      para pasarela (prueba vs. real) y, si es posible, proyectos de
      Supabase distintos.
- [ ] Toda variable que el código usa (`process.env.X` en el repo) existe
      en el entorno correspondiente; y no hay variables huérfanas con
      llaves viejas sin rotar.
- [ ] **Deployment Protection** en previews: abre una URL de preview sin
      sesión (`curl -sI <preview>`); debe responder 401 o redirigir al
      login de Vercel. Si responde 200, cualquiera con el enlace ve la app
      con datos de prueba o reales. Para auditar una preview protegida usa
      `vercel curl` (ver la skill de despliegues protegidos si existe).
- [ ] **Producción = `main`**: el despliegue de producción viene del último
      commit aprobado de `main` (compara `vercel inspect` con `git log main -1`).
- [ ] **Plan**: si la app es comercial (cobra, tiene clientes o publicidad)
      y el proyecto está en el plan Hobby, es un hallazgo `proveedor`
      (ver [restricciones-proveedores.md](restricciones-proveedores.md)).
- [ ] `vercel.json` / `next.config`: cabeceras de seguridad, `crons` con
      ruta protegida por `CRON_SECRET`, sin `rewrites` hacia orígenes
      ajenos sin necesidad.
- [ ] Región de funciones cercana a la región de Supabase (latencia y,
      si aplica, residencia de datos).
- [ ] Integración de GitHub: el repo es privado o, si es público, no tiene
      `docs/auditoria/` ni datos de prueba reales.
- [ ] Firewall/WAF: si hay endpoints costosos (IA, envío de correo,
      login), recomienda límite de tasa; regístralo como `media` si no hay.

## B2 · Supabase

```bash
npx supabase projects list            # proyecto vinculado, región, estado
npx supabase migration list           # LOCAL vs REMOTO: migraciones sin aplicar o aplicadas sin archivo
npx supabase db lint --linked         # errores en funciones plpgsql (si tu versión lo soporta)
npx supabase inspect db table-stats --linked   # tamaño y filas por tabla (detectar tablas inesperadas)
```

Con Docker disponible, además `npx supabase db diff --linked` (deriva entre
el esquema remoto y las migraciones). Si hay un conector o MCP de Supabase,
usa sus **asesores de seguridad y rendimiento** (`get_advisors`) y su
consulta SQL de solo lectura; si no, pide al usuario que abra
Dashboard → Advisors → Security Advisor y te pegue el resultado, o que
corra en el SQL Editor estas consultas (todas son `SELECT`):

```sql
-- 1. Tablas de public SIN RLS (deben ser cero)
select c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public' and c.relkind = 'r' and not c.relrowsecurity;

-- 2. Políticas vigentes (contrástalas con las migraciones)
select tablename, policyname, cmd, roles, qual, with_check
from pg_policies where schemaname in ('public', 'storage') order by 1, 2;

-- 3. Funciones SECURITY DEFINER sin search_path fijo
select p.proname from pg_proc p join pg_namespace n on n.oid = p.pronamespace
where n.nspname = 'public' and p.prosecdef
  and not exists (select 1 from unnest(coalesce(p.proconfig, '{}')) cfg where cfg like 'search_path=%');

-- 4. Vistas de public sin security_invoker (saltan RLS)
select c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public' and c.relkind = 'v'
  and not coalesce('security_invoker=true' = any(c.reloptions), false);

-- 5. Buckets públicos
select id, public from storage.buckets;

-- 6. Funciones de public ejecutables por anon
select routine_name from information_schema.routine_privileges
where grantee = 'anon' and routine_schema = 'public';
```

Verifica:

- [ ] `migration list` sin diferencias: una migración local no aplicada
      significa que **la política que viste en el código no existe en
      producción** (eleva la severidad del hallazgo de A2 asociado). Una
      remota sin archivo local significa cambios hechos a mano en el
      dashboard, fuera del método.
- [ ] Consultas 1, 3, 4: cero filas. 5: solo buckets públicos documentados.
      6: solo funciones pensadas para visitantes.
- [ ] **Auth** (Dashboard → Authentication, o `supabase/config.toml`):
      confirmación de correo activa; `Site URL` = dominio de producción;
      URL de redirección sin comodines amplios (`https://*.vercel.app/**`
      permite que cualquier app de Vercel reciba tokens); expiración de
      OTP corta; longitud mínima de contraseña; registro abierto solo si
      el modelo de negocio lo pide; SMTP propio para producción (el
      integrado tiene límites bajos y no es para usuarios reales).
- [ ] Llaves: la `service_role`/`sb_secret_` no se usa en ninguna variable
      pública (cruza con B1). Si se sospecha exposición, recomendar
      **rotar** (Dashboard → Settings → API keys) — lo hace el usuario.
- [ ] Edge Functions: `verify_jwt` activo salvo webhooks que verifican firma.
- [ ] Copias de seguridad / PITR acordes al plan y a la criticidad de los datos.
- [ ] Región del proyecto acorde a la residencia de datos declarada en
      `04-conceptual.md`.
- [ ] Plan gratuito: los proyectos inactivos se pausan; si la app ya tiene
      usuarios reales, es un hallazgo `proveedor` de severidad `media`.

## Qué reportar

Cada diferencia entre repo y despliegue es un hallazgo (categoría
`despliegue`), con el comando que la muestra como evidencia. Cuando un
hallazgo de código se confirma en el despliegue, cítalo en
`relacionados` con el ID del equipo A para que `consolidar` lo fusione.
