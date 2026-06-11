# HY3D v2 - Estructura actual del proyecto

Documento generado para describir el estado real del workspace del repo HY3D, incluyendo carpetas versionadas y carpetas locales ignoradas por Git.

## Resumen rapido

Este repo contiene tres piezas principales:

- `hy3d_v2/`: core del sistema HY3D v2, scripts, tests, assets de prueba, documentacion maestra y herramientas de benchmark.
- `hy3d_local_connector_addon/`: add-on principal actual para Blender, conectado al flujo local TripoSR.
- `hy3d_v2_clean_addon/`: add-on limpio/paquetizado anterior, con una copia embebida del core minimo.

Tambien existen carpetas locales de ejecucion, smoke tests, exports y builds (`HY3D_EXPORTS/`, `dist/`, `*_workspace`, etc.). Esas carpetas son parte del workspace operativo, pero no deben versionarse.

## Raiz del repo

### `.git/`

Carpeta interna de Git. Guarda historial, ramas, configuracion local del repo y objetos. No se edita manualmente.

Estado actual relevante:

- `main` esta por delante de `origin/main`.
- Hay commits locales de Fase 3 y Fase 4 pendientes de push.

### `.gitignore`

Define que no se sube a Git:

- caches de Python;
- workspaces locales;
- outputs de motor;
- ZIPs generados;
- `dist/`;
- `HY3D_EXPORTS/`;
- `hy3d_local_config.json`;
- reportes pesados/generados de benchmark.

Mantiene como excepcion versionable el fixture:

- `hy3d_v2/test_assets/result_package_sample.zip`

### `hy3d_local_config.json`

Configuracion local de maquina. Esta ignorada por Git.

Uso:

- permite definir rutas locales como proyecto, motor, wrapper o carpeta de exports;
- evita hardcodear rutas personales dentro del add-on.

No debe versionarse porque puede contener rutas especificas de la PC.

### `hy3d_v2_addon.zip`

ZIP local generado. Esta ignorado por Git por la regla `*.zip`.

Uso:

- artefacto de distribucion/manual testing;
- puede borrarse y regenerarse.

### `dist/`

Carpeta de distribucion local. Ignorada por Git.

Uso:

- contiene ZIPs de add-ons generados por scripts de packaging;
- no debe contener codigo fuente unico;
- se puede limpiar/regenerar.

### `.pytest_cache/`

Cache local de pytest. Ignorada por Git.

Uso:

- acelera ejecuciones de tests;
- no contiene logica del proyecto;
- se puede borrar sin riesgo.

## Add-on principal actual

### `hy3d_local_connector_addon/`

Contiene el add-on de Blender `HY3D Local Connector`. Es la superficie principal actual para el flujo local:

1. seleccionar imagen;
2. ejecutar TripoSR local mediante wrapper;
3. importar `result_package.zip`;
4. revisar candidatos;
5. aceptar manualmente un objeto seleccionado;
6. exportar STL solo desde `accepted_model.glb`;
7. copiar artefactos finales a `HY3D_EXPORTS/job_<id>/`.

#### `hy3d_local_connector_addon/hy3d_local_connector/__init__.py`

Archivo principal del add-on. Contiene:

- metadata `bl_info`;
- resolucion de rutas por env/config/defaults relativos;
- estado UI (`no_job`, `engine_generated`, `imported_to_hy3d`, `candidate_imported`, `accepted`, `stl_exported`, `stl_validated`);
- operadores de Blender;
- panel de UI;
- integracion con el core `hy3d_v2.hy3d_core`;
- importacion de candidatos original/light/meshfix/meshlab;
- flujo de accepted y STL;
- sync a `HY3D_EXPORTS`;
- selector de `repair_profile`;
- visualizacion de `input_quality`.

Este archivo se toca cuando se modifica la experiencia dentro de Blender o la conexion con el motor local.

#### `hy3d_local_connector_addon/hy3d_local_connector/__pycache__/`

Cache Python generado al importar el add-on fuera o dentro de Blender. Ignorado por Git.

## Core principal HY3D

### `hy3d_v2/`

Paquete principal del proyecto. Contiene el core reutilizable fuera de Blender, scripts, tests, assets y documentacion.

### `hy3d_v2/__init__.py`

Marca `hy3d_v2` como paquete Python.

### `hy3d_v2/hy3d_core/`

Core funcional. Aqui debe vivir la logica reutilizable, no atada a Blender.

#### `hy3d_v2/hy3d_core/job_service.py`

Servicio central de jobs. Maneja:

- creacion de jobs;
- estructura de carpetas;
- `job_manifest.json`;
- empaquetado `job_package.zip`;
- importacion segura de `result_package.zip`;
- validacion de `model.glb`;
- generacion de reportes;
- benchmark/reparacion de candidatos;
- promocion manual a `accepted_model.glb`;
- exportacion STL solo desde accepted;
- versionado inicial y `create_new_version_from_accepted`.

Es una de las piezas mas importantes del sistema.

#### `hy3d_v2/hy3d_core/models.py`

Dataclasses compartidas:

- `ReferenceView`;
- `ReviewPayload`;
- `JobPaths`.

Sirven para mantener contratos internos claros entre servicios.

#### `hy3d_v2/hy3d_core/input_quality/`

Modulo de Fase 4 para analizar calidad de imagen de entrada.

Archivos:

- `__init__.py`: exporta `analyze_input_image`.
- `service.py`: implementa el analisis.

Genera datos como:

- dimensiones;
- modo de imagen;
- alpha;
- aspect ratio;
- si es demasiado pequena;
- contraste;
- complejidad estimada de fondo;
- status y warnings.

Reporte generado por job:

- `versions/<version_id>/validation/input_quality_report.json`

#### `hy3d_v2/hy3d_core/validation/`

Validacion tecnica de candidatos GLB y calidad de malla.

Archivos:

- `service.py`: analiza `model.glb`, calcula metricas y warnings.
- `__init__.py`: expone el modulo.

Reportes relacionados:

- `candidate_validation_report.json`;
- `mesh_quality_report.json`.

Usa dependencias opcionales como `trimesh` y degrada de forma controlada si alguna no existe.

#### `hy3d_v2/hy3d_core/repair/`

Perfiles y backends de reparacion geometrica.

Archivos:

- `service.py`: contiene `REPAIR_PROFILES`, reparacion light/meshfix/meshlab y comparacion.
- `__init__.py`: exporta `REPAIR_PROFILES` y `run_repair_benchmark`.

Perfiles actuales:

- `safe_light`;
- `visual_preserve`;
- `printability`;
- `aggressive_close_holes`.

Reportes relacionados:

- `repair_report_light.json`;
- `repair_report_meshfix.json`;
- `repair_report_meshlab.json`;
- `repair_comparison_report.json`.

Regla critica: ningun candidato reparado se acepta automaticamente y ninguno exporta STL.

#### `hy3d_v2/hy3d_core/stl/`

Validacion y exportacion STL.

Archivos:

- `service.py`: exporta STL desde accepted y valida printability.
- `__init__.py`: expone el modulo.

Reportes relacionados:

- `stl_validation_report.json`;
- `printability_report.json`.

Regla critica: solo `accepted_model.glb` puede producir `accepted_model.stl`.

#### `hy3d_v2/hy3d_core/utils/`

Helpers pequenos compartidos.

Archivos:

- `files.py`: `ensure_dir`, `copy_file`, `read_json`, `write_json`, `utc_now_iso`.
- `__init__.py`: marcador de paquete.

#### `hy3d_v2/hy3d_core/jobs/`

Modulo reservado para logica futura relacionada con jobs. Actualmente funciona como paquete/namespace.

#### `hy3d_v2/hy3d_core/packaging/`

Modulo reservado para logica futura de empaquetado. Actualmente funciona como paquete/namespace.

#### `hy3d_v2/hy3d_core/versions/`

Modulo reservado para reforzar versionado avanzado. Actualmente funciona como paquete/namespace.

#### `hy3d_v2/hy3d_core/__pycache__/` y subcarpetas `__pycache__/`

Caches Python generados por imports/tests. Ignorados por Git.

## Add-on legacy / superficie anterior

### `hy3d_v2/blender_addon/`

Add-on anterior `HY3D v2`. Sigue en el repo por compatibilidad/tests, pero la superficie principal operativa actual es `hy3d_local_connector_addon`.

#### `hy3d_v2/blender_addon/__init__.py`

Contiene operadores/panel de Blender para el flujo HY3D v2 original:

- crear job package;
- importar result package;
- importar candidato;
- guardar review;
- aceptar objeto seleccionado;
- exportar STL;
- opciones de cloud worker antiguas.

No es el add-on recomendado para el flujo local TripoSR actual.

## Add-on limpio empaquetado anterior

### `hy3d_v2_clean_addon/`

Add-on limpio anterior con una copia embebida del core minimo.

Uso:

- referencia historica/compatibilidad;
- pruebas de empaquetado/import fuera de Blender;
- no es el foco principal de cambios nuevos si el flujo objetivo es Local Connector.

### `hy3d_v2_clean_addon/hy3d_v2_clean/__init__.py`

Entrada principal del add-on limpio.

### `hy3d_v2_clean_addon/hy3d_v2_clean/hy3d_core/`

Copia embebida de partes del core:

- `job_service.py`;
- `models.py`;
- `validation/`;
- `stl/`;
- `utils/`;
- namespaces `jobs/`, `packaging/`, `versions/`.

Importante: esta copia puede quedar desfasada respecto a `hy3d_v2/hy3d_core`. Antes de distribuir este add-on conviene revisar si necesita sincronizacion.

### `hy3d_v2_clean_addon/**/__pycache__/`

Caches Python ignorados por Git.

## Scripts

### `hy3d_v2/scripts/`

Herramientas de linea de comandos para operar el core sin Blender.

Archivos actuales:

- `create_job_package.py`: crea paquete de job desde inputs.
- `create_result_package.py`: arma un `result_package.zip` compatible.
- `import_result_package.py`: importa un resultado al workspace HY3D.
- `export_stl.py`: exporta STL desde accepted.
- `validate_candidate.py`: valida candidato GLB.
- `run_quality_benchmark.py`: ejecuta benchmark de Fase 3 en modo fixture, packages o wrapper explicito.
- `package_blender_addon.py`: empaqueta add-on legacy.
- `package_blender_clean_addon.py`: empaqueta add-on limpio.
- `package_blender_local_connector.py`: empaqueta `HY3D Local Connector`.

## Tests

### `hy3d_v2/tests/`

Suite automatizada del proyecto.

Archivos:

- `conftest.py`: setup basico para imports.
- `test_phase1_flow.py`: flujo central job -> result -> accepted -> STL, contratos de seguridad y versionado inicial.
- `test_path_validation.py`: validacion de rutas y bloqueos.
- `test_cloud_worker.py`: flujo cloud worker legacy/Drive.
- `test_local_connector_addon.py`: helpers y flujo del add-on local.
- `test_clean_addon.py`: add-on limpio.
- `test_addon_contract.py`: contratos del add-on.
- `test_quality_benchmark.py`: benchmark Fase 3.
- `test_phase4_input_quality_repair_profiles.py`: input quality y perfiles de reparacion.

Estado reciente:

- `python -m pytest hy3d_v2\tests -q`
- resultado registrado: `74 passed, 1 skipped`.

### `hy3d_v2/tests/__pycache__/`

Cache local de tests. Ignorado por Git.

## Assets de prueba

### `hy3d_v2/test_assets/`

Fixtures pequenos para tests y smoke flows.

Contenido relevante:

- `sample_input.png`: imagen minima usada por tests.
- `real_smoke_input.png`: input mas realista para smoke local.
- `sample_model.glb`: modelo GLB fixture.
- `result_package_sample.zip`: ZIP fixture versionado explicitamente aunque los ZIPs generales esten ignorados.

No poner aqui assets pesados, privados o generados salvo que sean fixtures pequenos y necesarios.

## Benchmark

### `hy3d_v2/benchmark_inputs/`

Lugar para entradas recomendadas del benchmark real.

Actualmente contiene:

- `README_BENCHMARK_INPUTS.md`: explica los tipos de imagen recomendados.

No debe llenarse con imagenes pesadas o privadas.

### `hy3d_v2/benchmark_reports/`

Carpeta para resultados del benchmark.

Versionado:

- se ignora casi todo;
- se versiona solo `manual_review_template.csv`.

Contenido posible local:

- `manual_review_template.csv`: plantilla editable versionada.
- `benchmark_summary.json`: generado, ignorado.
- `benchmark_summary.csv`: generado, ignorado.
- `_benchmark_workspace/`: workspace temporal generado, ignorado.

## Documentacion

### `hy3d_v2/docs/`

Documentacion oficial del proyecto.

Archivo principal:

- `HY3D_V2_MASTER_DOCUMENT.md`

Regla del proyecto: no crear documentacion paralela para el plan tecnico principal salvo solicitud explicita. Este archivo raiz (`PROJECT_STRUCTURE.md`) existe porque fue pedido explicitamente como mapa de carpetas.

## Configuracion

### `hy3d_v2/config/`

Configuraciones de ejemplo versionables.

Archivo:

- `external_engines.example.json`: ejemplo seguro para motores externos.

No poner aqui configuraciones personales reales; usar `hy3d_local_config.json` ignorado.

## Notebooks

### `hy3d_v2/notebooks/`

Notebooks de worker externo/historico.

Archivo:

- `HY3D_worker_colab.ipynb`

Uso:

- flujo externo compatible con `job_package.zip` -> `result_package.zip`;
- no forma parte del flujo local TripoSR directo;
- no debe romper el contrato universal `result_manifest.json + model.glb`.

## Workspaces y outputs locales

Estas carpetas existen en el workspace actual, pero estan ignoradas por Git. Contienen ejecuciones reales, smokes o resultados temporales.

### `hy3d_local_connector_workspace/`

Workspace local principal del `HY3D Local Connector`.

Estructura tipica:

```text
jobs/<job_id>/
  job_manifest.json
  input/
  multi_view/
  instructions/
  versions/v1/
    source/
    engine_output/
    validation/
    blender_review/
    edited/
    accepted/
```

Uso:

- jobs reales creados/importados desde el add-on local;
- no se versiona;
- puede crecer con resultados de pruebas.

### `hy3d_local_connector_workspace_smoke/`

Workspace temporal de smoke tests del conector local.

Uso:

- validar flujo GLB/STL sin contaminar el workspace principal.

### `hy3d_local_connector_status_smoke/`

Workspace temporal usado para probar estados y trazabilidad del conector local.

Uso:

- validar `local_engine_status.json`;
- comprobar transiciones como `engine_generated` -> `imported_to_hy3d`.

### `hy3d_local_connector_mesh_gate_smoke/`

Workspace temporal usado para probar mesh quality gate y candidatos reparados.

Uso:

- validar `mesh_quality_report.json`;
- validar `repair_report_*.json`;
- validar rutas de candidatos reparados.

### `hy3d_v2_clean_workspace/`

Workspace local del add-on limpio anterior.

Uso:

- pruebas/flujo legacy del add-on limpio;
- ignorado por Git.

### `_workspace_clean/`

Workspace auxiliar local.

Uso:

- pruebas o ejecuciones limpias fuera de los workspaces principales;
- no debe contener fuente unica.

### `hy3d_v2/_workspace/`

Fallback local que puede crear el add-on legacy cuando se importa fuera de Blender.

Uso:

- pruebas fuera de Blender;
- debe tratarse como generado/local.

### `hy3d_v2/jobs/`

Carpeta esperada para jobs si se usa `hy3d_v2` como root de workspace.

Uso:

- puede contener ejecuciones locales si scripts/core apuntan a `hy3d_v2`;
- no debe usarse para guardar codigo fuente.

## Exports finales

### `HY3D_EXPORTS/`

Carpeta local de entrega/inspeccion final. Ignorada por Git.

El conector local copia aqui, por job:

```text
HY3D_EXPORTS/job_<id>/
  accepted_model.glb
  accepted_model.stl
  stl_validation_report.json
  printability_report.json
```

Uso:

- ruta facil para encontrar resultados finales;
- no es la fuente canonica del job, sino una copia de salida.

Fuente canonica:

- `hy3d_local_connector_workspace/jobs/<job_id>/versions/<version_id>/accepted/`

## Archivos generados que pueden aparecer

### `__pycache__/` y `*.pyc`

Caches Python. Ignorados.

### `*.zip`

ZIPs generados. Ignorados salvo fixture especifico:

- `hy3d_v2/test_assets/result_package_sample.zip`

### `*.log`

Logs locales. Ignorados.

### `*.blend1`, `*.blend2`, `*.blend@`, `*.blend~`

Backups temporales de Blender. Ignorados.

## Contratos clave del proyecto

1. `model.glb` es candidato original.
2. `repaired_candidate_light.glb`, `repaired_candidate_meshfix.glb` y `repaired_candidate_meshlab.glb` son candidatos reparados.
3. Ningun candidato original o reparado exporta STL directamente.
4. Ningun candidato reparado se acepta automaticamente.
5. Solo el objeto seleccionado manualmente puede convertirse en `accepted_model.glb`.
6. Solo `accepted_model.glb` puede generar `accepted_model.stl`.
7. Todo resultado final se copia a `HY3D_EXPORTS/job_<id>/`.
8. El core debe seguir funcionando fuera de Blender.
9. El add-on debe llamar al core, no duplicar la logica critica.
10. Workspaces, outputs, ZIPs generados, configs locales y caches no se versionan.

## Que tocar segun el tipo de cambio

- Logica de jobs, manifests, accepted o STL: `hy3d_v2/hy3d_core/job_service.py`.
- Calidad de input: `hy3d_v2/hy3d_core/input_quality/`.
- Validacion de GLB/malla: `hy3d_v2/hy3d_core/validation/`.
- Reparacion de candidatos: `hy3d_v2/hy3d_core/repair/`.
- STL/printability: `hy3d_v2/hy3d_core/stl/`.
- UI de Blender local: `hy3d_local_connector_addon/hy3d_local_connector/__init__.py`.
- Scripts CLI: `hy3d_v2/scripts/`.
- Tests: `hy3d_v2/tests/`.
- Documentacion tecnica principal: `hy3d_v2/docs/HY3D_V2_MASTER_DOCUMENT.md`.
- Mapa de estructura del workspace: este archivo `PROJECT_STRUCTURE.md`.
