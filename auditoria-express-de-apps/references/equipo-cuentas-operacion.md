# Equipo D · Cuentas, operación y agente

La app puede estar bien construida y aun así caer si alguien entra a la
cuenta de GitHub, Vercel o Supabase del dueño, si no hay copia de seguridad
el día que se borra una tabla, o si el agente que construye todo tiene más
permisos de los que necesita. Este equipo mira **lo que rodea a la app**.

Gran parte de esta revisión vive en paneles que solo el dueño ve. El agente
corre lo que pueda por CLI y le hace al usuario **máximo 3 preguntas a la
vez**, de sí/no, con la recomendación incluida. Lo que no se pueda
verificar queda como hallazgo `info` con la pregunta pendiente.

Categorías: `cuentas`, `operacion`, `agente`.

## D1 · Cuentas y accesos

Comandos de solo lectura:

```bash
gh auth status                                         # cuenta y alcances del token del CLI
gh repo view --json visibility,owner,securityAndAnalysis   # privado/público, secret scanning, push protection
gh api repos/{owner}/{repo}/collaborators --jq '.[] | [.login, .role_name] | @tsv'
gh api repos/{owner}/{repo}/branches/main/protection 2>/dev/null || echo "main sin protección"
gh secret list                                          # NOMBRES de secretos de Actions (sin valores)
gh api orgs/{org} --jq .two_factor_requirement_enabled  # si el repo es de una organización
vercel whoami && vercel teams ls                        # equipo de Vercel
npx supabase orgs list && npx supabase projects list   # organización y proyectos de Supabase
```

Verifica (pregunta al usuario lo que no salga por CLI):

- [ ] **2FA activo** en GitHub, Vercel, Supabase, la pasarela de pago, el
      proveedor de IA, el de correo y el registrador del dominio. Sin 2FA en
      cualquiera de ellas → `alta`.
- [ ] Correo y métodos de recuperación de esas cuentas a nombre del dueño
      (no de un exempleado o de quien "le ayudó a montar").
- [ ] **Miembros**: solo personas activas, con el rol mínimo. Los
      colaboradores externos, con fecha de salida. Nadie con rol de dueño
      sin necesidad.
- [ ] **Tokens**: tokens personales de GitHub, Vercel y Supabase sin uso
      se revocan; los que usa CI tienen alcance mínimo y vencimiento.
- [ ] Rama `main` protegida (sin push directo ni force-push; requiere PR).
- [ ] Secret scanning y push protection activos en GitHub si el plan lo permite.
- [ ] Cuenta de la **pasarela** y de **IA** con topes: límite de gasto
      mensual en el proveedor de IA, alertas de facturación.
- [ ] Los servicios están a nombre de la **organización o del dueño**, no
      de la cuenta personal del desarrollador.

## D2 · Operación, continuidad y dominio

- [ ] **Copias de seguridad**: plan de Supabase con copias acordes al
      valor de los datos; PITR si se mueve dinero. **Restauración probada al
      menos una vez** (en un proyecto aparte). Copia sin restaurar = `media`.
- [ ] **Monitoreo**: errores del servidor y del cliente llegan a una
      herramienta (Sentry u otra) con alerta a una persona; sin datos
      personales en los eventos. Vercel Analytics o equivalente para uso.
- [ ] **Alertas** de facturación y de uso en Vercel (Spend Management) y
      Supabase (spend cap o alertas): un ataque de abuso se nota primero
      en la factura.
- [ ] **Procedimiento de incidente**: existe `docs/incidentes/llave-filtrada.md`
      (lo crea `auditar.py automatizar`) y el dueño sabe dónde está.
- [ ] **Dominio y correo** (si la app usa dominio propio):
      ```bash
      dig +short TXT DOMINIO                 # SPF (v=spf1 …)
      dig +short TXT _dmarc.DOMINIO          # DMARC (v=DMARC1; p=quarantine o reject)
      dig +short CNAME resend._domainkey.DOMINIO   # DKIM (el selector depende del proveedor)
      dig +short CAA DOMINIO
      ```
      Sin SPF/DKIM/DMARC los correos de la app caen en spam y el dominio
      se puede suplantar → `media`. Revisa también el vencimiento del
      dominio y subdominios que apunten a servicios dados de baja
      (`CNAME` a un proyecto de Vercel que ya no existe = toma de subdominio).
- [ ] **Datos personales al terminar**: hay forma de exportar y borrar la
      cuenta de un usuario (Ley 1581 / equivalente).

## D3 · Seguridad del agente que construye

En este método el agente ejecuta comandos, tiene sesión en los CLI y lee
el repositorio. Revisa:

- [ ] `.claude/settings.json` y `.claude/settings.local.json` del proyecto:
      sin permisos amplios como `Bash(*)` o modo que omita confirmaciones
      para comandos que despliegan, borran o empujan (`vercel --prod`,
      `supabase db push`, `git push --force`, `rm -rf`).
- [ ] `.mcp.json` y configuración de conectores: sin tokens escritos en
      el archivo (van en variables de entorno); conectores con el alcance
      mínimo (p. ej. MCP de Supabase en modo solo lectura para auditar).
- [ ] El agente nunca trabajó con la `service_role` exportada en la
      terminal ni la pegó en el chat: si ocurrió, **rotarla** (los
      historiales de la sesión la conservan).
- [ ] `CLAUDE.md` del proyecto con las reglas del método y de lecciones;
      sin secretos ni datos personales.
- [ ] Hooks o automatizaciones del agente revisados: nada que envíe
      código o datos a servicios externos sin que el dueño lo sepa.

## Qué reportar

Una pregunta sin responder es un hallazgo `info` ("¿hay 2FA en Supabase?
pendiente de confirmar"). Una respuesta negativa es un hallazgo con su
severidad. Las acciones de este equipo casi siempre las hace **el dueño**:
redacta la propuesta como pasos para él, no como código.
