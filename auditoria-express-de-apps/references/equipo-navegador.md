# Equipo C · Navegador (interfaz y peticiones)

Mira la app como la ve cualquiera: lo que descarga, lo que pide, lo que
responde el servidor y lo que se puede hacer con la clave pública que el
navegador recibe. **Solo en las URL que el usuario autorizó en `plan.md`.**

Herramientas, en orden de preferencia: el navegador del entorno (lectura de
página, red y consola), `curl`, y `auditar.py escanear --incluir-build`
para el bundle local. Prefiere leer texto y red antes que capturas.

## C1 · Interfaz, cabeceras y peticiones

1. **Cabeceras** de la página principal y de una ruta protegida:
   ```bash
   curl -sI https://APP/ | sed -n '1,40p'
   ```
   - [ ] `Strict-Transport-Security` (Vercel la pone en sus dominios; revisa el dominio propio).
   - [ ] `Content-Security-Policy` (al menos `frame-ancestors 'self'`, `object-src 'none'`, `base-uri 'self'`).
   - [ ] `X-Content-Type-Options: nosniff`, `Referrer-Policy`, `Permissions-Policy`.
   - [ ] Sin `X-Powered-By` ni cabeceras que revelen versiones.
   - [ ] Una ruta protegida sin sesión redirige al login y no envía datos en el HTML.
2. **Bundle**: en la red, lista los `/_next/static/**/*.js` cargados. Busca
   (en el navegador o con el barrido de `.next/static`):
   - [ ] Ningún JWT con `"role":"service_role"` (decodifica la parte central
         en base64; la `anon` es pública y está bien).
   - [ ] Ningún `sb_secret_`, `sk_live_`, `sk-ant-`, `prv_prod_`, URL de Postgres con contraseña.
   - [ ] Sin archivos `.map` públicos (`curl -sI https://APP/_next/static/…js.map` → 404).
   - [ ] Sin URL internas, correos de administradores ni comentarios con datos.
3. **Peticiones** durante un recorrido normal (login → el ciclo de E1):
   - [ ] Las peticiones a `*.supabase.co` llevan `apikey` = `anon`/`publishable`
         y `Authorization: Bearer` = token **del usuario**, nunca la `service_role`.
   - [ ] Las respuestas no traen columnas de más (correo, teléfono, notas
         internas de otros usuarios): `select=*` desde el cliente es una
         señal; los datos de otros solo deberían salir por vistas o
         consultas que eligen columnas.
   - [ ] Los errores no muestran mensajes de Postgres, trazas ni rutas del servidor.
   - [ ] Cookies de sesión con `Secure` y `SameSite`; nada sensible en
         `localStorage` salvo lo que el SDK guarda por diseño.
   - [ ] Formularios de login/registro/recuperación: mensajes que no
         revelan si un correo existe; el enlace de recuperación vuelve al
         dominio propio.
   - [ ] Sin llamadas a terceros inesperadas (analítica no declarada,
         scripts de CDNs desconocidos).
4. **Consola**: errores, avisos de hidratación o de CSP que indiquen
   configuraciones a medias.
5. **Realtime**: si hay WebSocket a `*.supabase.co/realtime`, revisa en
   los mensajes que los canales de broadcast/presence se unen como
   privados y que no llegan eventos de otras organizaciones.
6. **Accesibilidad y rendimiento** (buenas prácticas): en 2-3 pantallas
   del ciclo E1, revisa con la lectura de la página que imágenes y campos
   tengan nombre accesible y que se pueda operar con teclado. Si el
   usuario lo aprueba (descarga un paquete), Lighthouse da números:
   `npx lighthouse URL --only-categories=accessibility,performance,best-practices --quiet --chrome-flags=--headless --output=json --output-path=docs/auditoria/FECHA/lighthouse.json`.
   Puntaje < 80 en accesibilidad → `media`; LCP > 2,5 s en móvil → `media` (`rendimiento`).

Fragmento de inspección (ejecútalo en la página con la herramienta de
JavaScript del navegador; solo lee y **no imprime valores**):

```js
(() => {
  const jwt = /eyJ[\w-]+\.eyJ[\w-]+\.[\w-]+/g, out = [];
  const roles = t => { try { return JSON.parse(atob(t.split('.')[1].replace(/-/g,'+').replace(/_/g,'/'))).role } catch { return '?' } };
  for (const s of [...document.scripts]) for (const m of (s.textContent.match(jwt) || [])) out.push({donde: 'script inline', rol: roles(m)});
  for (const k of Object.keys(localStorage)) out.push({donde: 'localStorage', clave: k, largo: localStorage.getItem(k).length});
  return out;
})()
```

## C2 · Acceso a datos desde fuera

Comprueba en la práctica lo que A2 vio en las migraciones. La clave
pública (`anon`) está en el bundle y **cualquiera la tiene**: lo que ella
permita hacer sin sesión, lo puede hacer cualquiera.

Toma la URL del proyecto de Supabase y la clave pública del bundle o de
`.env.example`; guárdalas en variables de la terminal, **sin imprimirlas**.
Lista de tablas: las de las migraciones (o la consulta 1-2 de B2).

```bash
# Lectura anónima, una fila por tabla: debe devolver [] o 401 en toda tabla privada
for t in perfiles organizaciones membresias bitacora; do
  printf '%s: ' "$t"
  curl -s -o /dev/null -w '%{http_code} ' "$SUPA_URL/rest/v1/$t?select=*&limit=1" -H "apikey: $SUPA_ANON"
  curl -s "$SUPA_URL/rest/v1/$t?select=*&limit=1" -H "apikey: $SUPA_ANON" | head -c 80; echo
done
```

- [ ] Toda tabla privada responde `[]` o error sin sesión. Una fila de
      datos = **crítico confirmado** (cualquiera puede descargar la tabla).
- [ ] `GET $SUPA_URL/rest/v1/` (esquema OpenAPI): si responde, anota qué
      tablas y funciones expone; nada que no deba ser visible.
- [ ] Storage: un archivo de un bucket privado no se descarga por su URL
      pública (`/storage/v1/object/public/<bucket>/<ruta>` → 400/404).
- [ ] Funciones RPC expuestas a `anon` (consulta 6 de B2): **solo** llama
      las que sean de lectura evidente; nunca una que inserte, actualice o
      envíe algo.
- [ ] Registro abierto: si `POST /auth/v1/signup` está habilitado y el
      modelo no lo pide (app solo por invitación), es un hallazgo. **No
      crees cuentas en producción** para comprobarlo: léelo de la
      configuración de Auth (B2).

**Con cuentas de prueba y solo en local o en un entorno de prueba que el
usuario nombró** (nunca en producción con datos reales):

- [ ] Usuario A, con su sesión, pide por la API filas de la organización
      de B (cambiando el `id` en la URL o en el filtro): debe recibir `[]`
      o 403. Repite con una Server Action/Route Handler que reciba un ID.
- [ ] Usuario sin rol de administrador intenta la acción de administrador
      (cambiar roles, ver bitácora) por la API, no solo por la interfaz.
- [ ] Un `update` que cambia `organizacion_id` de una fila propia a otra
      organización es rechazado (`with check`).

Nunca escribas en el informe tokens de sesión, correos de prueba ni
contraseñas: describe la prueba ("usuario de prueba A, rol miembro").

## Qué reportar

Categoría `navegador` para lo observado en red/cabeceras/bundle, `rls`
para accesos indebidos confirmados. La evidencia es la petición (método,
ruta, código de estado, tamaño de la respuesta), con los secretos
enmascarados. Cita en `relacionados` el ID del hallazgo de código que
explica la causa, si lo conoces.
