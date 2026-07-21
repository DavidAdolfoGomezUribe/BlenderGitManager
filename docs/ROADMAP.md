# Roadmap

## Entregado en 0.1.8

- Corregida la excepción de `UILayout.prop_search` que detenía el dibujo de History.
- Carriles y conexiones del Git Graph renderizados con colores RGBA por carril.
- Nodos centrados en la misma fila que el hash, mensaje, autor, fecha y referencias.
- Vista History compacta para que el gráfico permanezca visible en ventanas bajas.
- Detalles del commit plegables y gráfico a ancho completo con scroll vertical.
- Pruebas visuales reales en Blender para merges y `Detached HEAD`.

## Entregado en 0.1.7

- Git Graph visual con carriles, bifurcaciones, merges y referencias.
- Búsqueda por autor, hash y mensaje, filtro de rama y carga incremental.
- Historial con archivos modificados y estadísticas por commit.
- Tags ligeros y anotados desde commits.
- Creación de ramas desde commits.
- Revert y checkout de commits con confirmación y recarga segura de la escena.

## Fase 2

- CRUD completo de remotos.
- Stash con mensaje e inclusión de untracked.
- Indicadores de upstream por rama.
- Publicación de ramas y tags.
- Pantalla dedicada para crear repositorios GitHub con README/licencia.

## Fase 3

- Merge controlado y detección previa de dirty working tree.
- Conflictos de texto: ours, theirs, resolved y editor externo.
- Conflictos `.blend`: backup de ambas variantes y selección explícita.
- Centro persistente de tareas y cancelación de árboles de procesos completos.
- Progreso LFS mediante parsing de stderr y eventos de transferencia.

## Fase 4

- Linux y macOS validados en CI.
- GitLab CLI/API y Bitbucket.
- Bloqueo de archivos grandes con proveedor compatible.
- Extracción y comparación de metadatos de escenas Blender.
- Pull requests, issues, releases y acciones.
- Flujos para equipos y convenciones de ramas.

## Deuda técnica conocida del MVP

- Añadir parser porcelain `-z` para nombres con saltos de línea o secuencias inusuales.
- Añadir localización inglés/español mediante traducciones de Blender.
- Persistir preferencias de sesión de forma controlada sin introducir rutas o secretos en `.blend`.
