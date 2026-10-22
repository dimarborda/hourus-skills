# Lecciones aprendidas (de la skill)

Patrones que se repiten al auditar apps hechas con Next.js + Supabase +
Vercel por personas que empiezan, y criterios que separan una auditoría
útil de una lista de alarmas. Léelos antes de lanzar los equipos. Cuando
una lección de un proyecto (`docs/06-lecciones-aprendidas.md`) valga para
todos, súbela aquí.

## Dónde suelen estar las fallas

- **La política que no se aplicó.** La migración con RLS existe en el
  repo, pero `supabase migration list` muestra que nunca llegó al remoto.
  Por eso el equipo B existe: el código no es la verdad de producción.
- **La tabla que se creó desde el dashboard.** Alguien "probó rápido" en el
  Table Editor; la tabla no tiene migración ni RLS. Aparece solo en las
  consultas al catálogo o en la prueba anónima de C2.
- **`service_role` para "arreglar" un error de permisos.** Cuando una
  política bloquea algo, la salida fácil es usar la llave que salta RLS.
  Busca cada uso de la `service_role` y pregunta por qué no basta RLS.
- **Server Actions como endpoints olvidados.** La página está protegida,
  la acción no. Cualquiera puede invocarla con el ID de otro.
- **`user_metadata` como rol.** Parece cómodo y lo edita el propio usuario.
- **Variables copiadas de un tutorial** con prefijo `NEXT_PUBLIC_` "para
  que funcione en el cliente".
- **Comodines en las URL de redirección de Auth** (`*.vercel.app`) que
  permiten a cualquier app de Vercel recibir el token.
- **Previews abiertas con datos reales**: la preview usa el mismo proyecto
  de Supabase que producción y su URL termina en un chat o un correo.
- **El secreto "borrado"**: se quitó del archivo, pero sigue en el
  historial de git y en despliegues anteriores. Sin rotación no hay arreglo.

## Cómo auditar mejor

- **Tres ángulos, una falla.** El mismo problema visto en código (A),
  despliegue (B) y navegador (C) es un hallazgo confirmado; visto en uno
  solo, es una hipótesis. Fusiona en vez de contar tres veces.
- **Probar lo que dice el código, no confiar en él.** "Hay RLS" se
  comprueba con una petición anónima, no leyendo la migración.
- **Datos, no conclusiones, a los subagentes.** El brief lleva la ruta,
  la lista y el barrido estático; nunca "creo que hay un IDOR en X".
- **Verificar los críticos con otro agente** antes de alarmar al usuario:
  un falso crítico gasta su confianza en el informe.
- **El barrido estático es un punto de partida**, no el informe: genera
  `posible`, y los agentes los confirman o descartan.
- **Cada hallazgo termina en un cambio concreto** y en una lección; sin
  propuesta, es ruido.
- **El usuario no técnico decide sobre riesgos, no sobre código.** Explica
  el riesgo en una frase ("cualquiera con el enlace ve los pagos") y qué
  tiene que hacer él (rotar, cambiar de plan, aceptar).

## Retroalimentación al método

- Si un mismo hallazgo aparece en dos proyectos distintos, el problema es
  del método: márcalo `alcance: metodo` y propón el cambio a la plantilla,
  la guía de construcción o el checklist de `diseno-express-de-apps`.
- Las lecciones del proyecto valen solo si el agente las lee: por eso
  `auditar.py iniciar` añade la regla al `CLAUDE.md` del proyecto.
- Una lección incumplida en la siguiente auditoría es más grave que el
  hallazgo original: el sistema de aprendizaje falló.
