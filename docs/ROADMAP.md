# Roadmap

## Fase 2

- CRUD completo de remotos.
- Stash con mensaje e inclusión de untracked.
- Tags ligeros y anotados.
- Historial con archivos de cada commit.
- `git show --name-status` y `git show --stat`.
- Creación de ramas desde commits.
- Indicadores de upstream por rama.
- Publicación de ramas y tags.
- Pantalla dedicada para crear repositorios GitHub con README/licencia.

## Fase 3

- Grafo visual con carriles, merges y filtros.
- Merge controlado y detección previa de dirty working tree.
- Revert y checkout con respaldo obligatorio.
- Conflictos de texto: ours, theirs, resolved y editor externo.
- Conflictos `.blend`: backup de ambas variantes y selección explícita.
- Centro persistente de tareas y cancelación de árboles de procesos completos.
- Progreso LFS mediante parsing de stderr y eventos de transferencia.
- Búsqueda por autor, hash, rama y mensaje.

## Fase 4

- Linux y macOS validados en CI.
- GitLab CLI/API y Bitbucket.
- Bloqueo de archivos grandes con proveedor compatible.
- Extracción y comparación de metadatos de escenas Blender.
- Pull requests, issues, releases y acciones.
- Flujos para equipos y convenciones de ramas.

## Deuda técnica conocida del MVP

- Ampliar la cancelación explícita del proceso actual a árboles completos de procesos auxiliares.
- Añadir parser porcelain `-z` para nombres con saltos de línea o secuencias inusuales.
- Añadir pruebas automatizadas dentro de Blender para registro, paneles y operadores.
- Añadir localización inglés/español mediante traducciones de Blender.
- Persistir preferencias de sesión de forma controlada sin introducir rutas o secretos en `.blend`.
