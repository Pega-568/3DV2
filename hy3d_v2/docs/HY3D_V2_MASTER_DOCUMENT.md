# HY3D v2 Master Document

## Resumen del proyecto
HY3D v2 es un sistema local para Blender orientado a un flujo GLB-first. La generación 3D pesada queda fuera de la PC local. El sistema local crea jobs, empaqueta entradas, importa resultados externos, valida candidatos, permite revisión/edición humana, promueve un GLB aceptado y exporta STL solo desde la versión aceptada activa.

## Objetivo final
Entregar un flujo estable y verificable:

1. Seleccionar imagen principal y vistas de referencia.
2. Crear `job_package.zip`.
3. Ejecutar generación externa fuera de Blender.
4. Importar `result_package.zip` con `model.glb`.
5. Revisar y editar el candidato en Blender.
6. Guardar el objeto editado como `accepted_model.glb`.
7. Exportar `accepted_model.stl` únicamente desde el aceptado activo.
8. Generar reportes JSON de validación.

## Decisiones de arquitectura
- El core nuevo vive en `hy3d_core` y no reutiliza el routing legacy.
- El add-on llama al core. No duplica la lógica de jobs, aceptación o STL.
- `hy3d_v2` es el core del sistema.
- `hy3d_v2_clean` es la interfaz principal de Blender.
- El add-on viejo `hy3d_v2` queda deprecated y no debe usarse como superficie principal.
- `model.glb` es candidato, no éxito final.
- `accepted_model.glb` es la fuente oficial para STL.
- `accepted_model.stl` es el único STL oficial del job.
- El sistema no depende de servidor permanente.
- La generación pesada queda preparada para ejecución externa por ZIP.

## Qué se descartó del sistema anterior
- Relief como núcleo.
- 2.5D como solución principal.
- Lógica 7A, 7B, 7C, 7X.
- `prefer_3d_if_safe`, `fallback_mode`, `volumetric_mode` y routing legacy.
- STL directo desde `model.glb`.
- Arquitectura multi-doc dispersa.
- Dependencia obligatoria de GPU local o servidor local persistente.

## Qué se reutiliza como idea
- Job aislado por carpeta.
- Artefactos JSON verificables.
- Validación ligera local antes de revisión humana.
- Blender como superficie de revisión, edición y promoción humana.

## Flujo completo GLB -> revisión humana -> STL
1. El usuario crea un job desde Blender o script.
2. El sistema guarda `job_manifest.json`, inputs y manifiestos multi-view.
3. El sistema crea `job_package.zip`.
4. Un worker externo produce `result_package.zip` con `model.glb`.
5. El sistema importa `model.glb`, crea `candidate_manifest.json` y `candidate_validation_report.json`.
6. El usuario importa el GLB candidato en Blender.
7. El usuario llena `manual_review.json`.
8. El usuario presiona `Use Selected Object as Accepted Model`.
9. El sistema exporta `accepted_model.glb`, guarda `accepted_manifest.json` y marca la versión como aceptada.
10. Solo entonces se permite exportar `accepted_model.stl`.
11. El sistema genera `stl_validation_report.json` y `printability_report.json`.

## Core mínimo implementado
- `create_job()`
- `create_job_package()`
- `import_result_package()`
- `save_manual_review()`
- `promote_selected_object_to_accepted()`
- `export_stl_from_accepted()`

## Modo remoto por IP
HY3D v2 ahora soporta dos modos de ejecución en el add-on HY3D Local Connector:

- `local`: Blender ejecuta el wrapper local TripoSR, importa `result_package.zip`, revisa candidatos y exporta STL desde el aceptado. Este flujo se mantiene intacto.
- `remote`: Blender actúa como cliente HTTP. El servidor recibe la imagen, ejecuta TripoSR/HY3D core, guarda candidatos/reportes, y espera que Blender suba el objeto aceptado manualmente.

En modo remoto corren en el servidor:

1. API FastAPI `server.hy3d_api.main:app`.
2. Workspace remoto del job.
3. Wrapper TripoSR portable, si `HY3D_ENGINE_ROOT` y `HY3D_WRAPPER_RUN` están configurados.
4. `hy3d_v2.hy3d_core.import_result_package()`.
5. Reparaciones y reportes de calidad.
6. Exportación STL desde `accepted_model.glb`.

Blender sigue haciendo:

1. Selección de imagen inicial.
2. Descarga e importación de candidatos para revisión visual.
3. Decisión humana de aceptación.
4. Export temporal del objeto seleccionado como GLB.
5. Subida de ese GLB al servidor como `accepted_model.glb`.
6. Descarga del paquete final.

Para iniciar el backend:

```powershell
uvicorn server.hy3d_api.main:app --host 0.0.0.0 --port 8000
```

Variables de entorno del servidor:

```text
HY3D_SERVER_WORKSPACE_ROOT
HY3D_SERVER_EXPORTS_ROOT
HY3D_ENGINE_ROOT
HY3D_WRAPPER_RUN
HY3D_JOB_TIMEOUT_SECONDS
HY3D_MAX_UPLOAD_MB
```

El add-on se configura en `Execution Mode = Remote`, sección `Remote Server`, con `Server URL` como `http://127.0.0.1:8000` o la IP LAN del servidor. El flujo remoto recomendado es:

1. `Check Remote Server`.
2. `Submit Image To Server`.
3. `Refresh Remote Job Status` hasta `candidate_ready_for_review`.
4. Descargar candidatos con `Download Original Candidate`, `Download Light Candidate`, `Download MeshFix Candidate` o `Download MeshLab Candidate`.
5. Revisar manualmente en Blender.
6. Seleccionar el objeto aceptado.
7. `Upload Selected As Accepted`.
8. `Request Remote STL Export`.
9. `Download Final Package`.

Reglas del modo remoto:

- `model.glb` es solo candidato original.
- `repaired_candidate_*.glb` son solo candidatos reparados.
- Ningún candidato se acepta automáticamente.
- Solo el objeto seleccionado manualmente en Blender se sube como `accepted_model.glb`.
- El servidor solo exporta `accepted_model.stl` desde `accepted_model.glb`.
- Las respuestas públicas no necesitan exponer rutas absolutas internas del servidor.

## Ejecución con Docker
La primera imagen Docker empaqueta solo el backend FastAPI. No incluye Blender, no descarga pesos pesados y no intenta instalar TripoSR completo durante el build.

Requisitos:

- Docker.
- Docker Compose.

Preparar entorno:

```bash
cp .env.docker.example .env
```

Construir:

```bash
docker compose build
```

Levantar:

```bash
docker compose up -d
```

Ver logs:

```bash
docker compose logs -f hy3d-api
```

Probar health:

```bash
curl http://localhost:8000/health
```

Modo fixture/dev:

```env
HY3D_SERVER_FIXTURE_RESULT_PACKAGE=hy3d_v2/test_assets/result_package_sample.zip
```

Con esa variable, `POST /api/jobs` puede validar el flujo remoto mínimo sin TripoSR real: crea job, importa el fixture como `model.glb`, genera reportes, permite subir `accepted_model.glb`, exporta STL desde el aceptado y descarga el paquete final.

Exponer por IP:

```text
http://<IP_SERVIDOR>:8000
```

Configurar Blender:

1. `Execution Mode = Remote`.
2. `Server URL = http://<IP_SERVIDOR>:8000`.
3. `Check Remote Server`.
4. Continuar con `Submit Image To Server`, descarga de candidatos, aceptación manual y paquete final.

Preparación para TripoSR real en servidor:

- Opción A: montar un TripoSR externo, por ejemplo `/opt/triposr-local:/opt/triposr-local:ro`.
- Definir `HY3D_ENGINE_ROOT=/opt/triposr-local`.
- Definir `HY3D_WRAPPER_RUN=/app/tools/triposr/run_triposr_local.ps1` o el wrapper Linux equivalente de una fase posterior.
- Opción B: crear una imagen worker futura separada.

Limitación actual: Docker valida la API y el modo fixture/dev. La integración completa de TripoSR real dentro de contenedor o mediante worker queda para la siguiente fase.

## Estructura del proyecto
```text
hy3d_v2/
  __init__.py
  blender_addon/
    __init__.py
  test_assets/
    sample_input.png
    sample_model.glb
    result_package_sample.zip
  hy3d_core/
    __init__.py
    job_service.py
    models.py
    jobs/
    packaging/
    validation/
      service.py
    stl/
      service.py
    versions/
    utils/
      files.py
  scripts/
    create_job_package.py
    create_result_package.py
    import_result_package.py
    validate_candidate.py
    export_stl.py
  notebooks/
    HY3D_worker_colab.ipynb
  config/
    external_engines.example.json
  jobs/
  docs/
    HY3D_V2_MASTER_DOCUMENT.md
  tests/
    conftest.py
    test_phase1_flow.py
    test_addon_contract.py
```

## Contratos JSON
### `job_manifest.json`
```json
{
  "job_id": "job_xxx",
  "created_at": "2026-05-19T00:00:00+00:00",
  "status": "awaiting_external_generation",
  "active_version": "v1",
  "active_accepted_version": null,
  "versions": [
    {
      "version_id": "v1",
      "source_type": "image_to_3d",
      "status": "awaiting_external_generation"
    }
  ]
}
```

### `multi_view_manifest.json`
```json
{
  "job_id": "job_xxx",
  "input_mode": "multiple_views",
  "primary_image": "input/primary_image.png",
  "reference_views": [
    {
      "path": "input/original_uploads/image_01.png",
      "view_type": "side"
    }
  ]
}
```

### `multi_view_validation_report.json`
```json
{
  "image_count": 2,
  "primary_image": "input/primary_image.png",
  "reference_views": [],
  "accepted_for_generation": true,
  "warnings": []
}
```

### `source/source_type.json`
```json
{
  "version_id": "v1",
  "source_type": "image_to_3d",
  "input_mode": "single_image",
  "primary_image": "versions/v1/source/primary_image.png"
}
```

### `engine_output/candidate_manifest.json`
```json
{
  "job_id": "job_xxx",
  "version_id": "v1",
  "candidate_path": "E:/.../model.glb",
  "imported_at": "2026-05-19T00:00:00+00:00",
  "validation_status": "needs_human_review"
}
```

### `validation/candidate_validation_report.json`
```json
{
  "candidate_path": "E:/.../model.glb",
  "exists": true,
  "readable_by_trimesh": false,
  "readable_by_pyvista": false,
  "bbox": null,
  "component_count": null,
  "is_empty": false,
  "flatness_warning": false,
  "validation_status": "needs_human_review",
  "warnings": []
}
```

### `blender_review/manual_review.json`
```json
{
  "job_id": "job_xxx",
  "version_id": "v1",
  "saved_at": "2026-05-19T00:00:00+00:00",
  "warnings": [],
  "visual_score": 4,
  "geometry_score": 4,
  "object_similarity": 4,
  "holes_or_artifacts": "minor",
  "usable_as_base": true,
  "repair_needed": "light",
  "notes": "usable candidate"
}
```

### `accepted/accepted_manifest.json`
```json
{
  "job_id": "job_xxx",
  "version_id": "v1",
  "source_candidate_path": "E:/.../model.glb",
  "accepted_model_path": "E:/.../accepted_model.glb",
  "accepted_object_name": "Candidate",
  "human_edited": true,
  "accepted_at": "2026-05-19T00:00:00+00:00",
  "accepted_source": "selected_blender_object"
}
```

### `accepted/stl_validation_report.json`
Contiene el estado técnico del STL y un subreporte `printability_report`.

### `accepted/printability_report.json`
Estados posibles implementados:
- `print_ready_candidate`
- `needs_cleanup`
- `validation_unavailable`

## Estructura de carpetas de jobs
```text
jobs/<job_id>/
  job_manifest.json
  input/
    primary_image.png
    original_uploads/
  multi_view/
    multi_view_manifest.json
    multi_view_validation_report.json
    selected_primary_view.json
  instructions/
    prompt.txt
  versions/
    v1/
      source/
      engine_output/
      validation/
      blender_review/
        screenshots/
      edited/
      accepted/
```

## Flujo de versionado
- `v1` nace desde imagen.
- `v2` y siguientes se preparan desde el `accepted_model.glb` activo.
- Nunca se sobrescribe una versión previa.
- El core ya incluye `create_new_version_from_accepted(...)`.
- La modificación IA desde GLB queda preparada estructuralmente, no operativa aún desde Blender.

## Flujo multi-imagen
- Existe `input_mode` con `single_image` y `multiple_views`.
- Se exige una imagen primaria.
- Se acepta una vista adicional en la UI MVP actual.
- Se generan `multi_view_manifest.json`, `multi_view_validation_report.json` y `selected_primary_view.json`.
- Las vistas adicionales hoy sirven como referencia y packaging, no como reconstrucción multi-view real.

## Flujo de generación externa
- El sistema local crea `job_package.zip`.
- El worker externo debe devolver `result_package.zip` compatible con el importador local actual.
- Existe un paquete de muestra local `test_assets/result_package_sample.zip` para demostrar el flujo sin IA externa.
- El notebook `notebooks/HY3D_worker_colab.ipynb` ahora cubre dos modos:
  - modo manual por subida directa de `job_package.zip`
  - modo `Cloud Worker` por Google Drive usando `incoming/processing/completed/failed/logs`
- El notebook implementa:
  - extracción segura del ZIP
  - lectura de `job_manifest.json`
  - localización de `input/primary_image.png`
  - normalización de imagen a PNG RGB
  - instalación de TripoSR Clean
  - ejecución de `run.py` con salida GLB
  - creación de `result_manifest.json`
  - empaquetado de `result_package.zip`
  - descarga manual o escritura en Google Drive
- Para compatibilidad con el core local actual, el notebook empaqueta:
  - `result_manifest.json` en la raíz del ZIP
  - `model.glb` en la raíz del ZIP
  - `engine_output/model.glb` como ruta semántica declarada en `candidate_path`
  - `logs/engine_log.txt`
- No hay dependencia actual de Colab, Hugging Face o Modal para que el core local funcione.

## Cloud Worker por Google Drive
Rutas configuradas:
- `CLOUD_ROOT_WINDOWS = "G:\\Mi unidad\\HY3D_V2_CLOUD"`
- `CLOUD_ROOT_COLAB = "/content/drive/MyDrive/HY3D_V2_CLOUD"`

Contrato de carpetas:
- `incoming/`
- `processing/`
- `completed/`
- `failed/`
- `logs/`
- `notebooks/`

Contrato de nombres de archivo:
- entrada desde Blender: `<job_id>_job_package.zip`
- resultado desde Colab: `<job_id>_result_package.zip`
- estado de resultado: `<job_id>_status.json`
- error de worker: `<job_id>_error.json`
- log de worker: `<job_id>_engine_log.txt`

Flujo semiautomático:
1. Blender crea `job_package.zip`.
2. `Send Job to Cloud` copia el ZIP a `incoming/<job_id>_job_package.zip`.
3. Colab toma un ZIP desde `incoming/`, lo mueve a `processing/` y ejecuta TripoSR.
4. Si el worker termina bien, escribe:
   - `completed/<job_id>_result_package.zip`
   - `completed/<job_id>_status.json`
5. Si falla, escribe:
   - `failed/<job_id>_error.json`
   - `failed/<job_id>_engine_log.txt`
   - copia de auditoría del `job_package.zip`
6. Blender usa `Check Cloud Results`.
7. Si existe el ZIP en `completed/`, `Import Cloud Result` reutiliza exactamente la lógica actual de `Import Result Package`.
8. El resto del flujo local no cambia: `Import Candidate GLB` -> revisión/edición -> `accepted_model.glb` -> `accepted_model.stl`.

Estado actual del add-on limpio:
- `Select Primary Image` ya valida `.png`, `.jpg`, `.jpeg`, `.webp`, `.avif`, `.bmp`.
- `Create Job Package` usa primero `primary_image_path`; `Use Sample Input` sigue siendo fallback manual explícito.
- `Send Job to Cloud` crea subcarpetas faltantes y escribe `cloud_status.json` local.
- `Check Cloud Results` detecta `completed`, `processing`, `failed` y `result_not_ready` sin polling.
- `Import Cloud Result` reutiliza `import_result_package()` del core actual.
- `Open Cloud Folder` abre la raíz cloud solo si la ruta existe.

## Validación geométrica
- Se ejecuta al importar `result_package.zip`.
- Usa `trimesh` si está disponible.
- Intenta marcar disponibilidad de PyVista sin convertirlo en requisito duro.
- Si una librería opcional falla o no existe, el sistema degrada y registra advertencias.
- La validación no autoacepta el modelo. Solo lo deja en `needs_human_review`.

## Revisión manual en Blender
Campos activos:
- `visual_score`
- `geometry_score`
- `object_similarity`
- `holes_or_artifacts`
- `usable_as_base`
- `repair_needed`
- `notes`

Regla implementada:
- Si `usable_as_base=true` con `visual_score < 3` o `geometry_score < 3`, se guarda advertencia en `manual_review.json`.

## Promoción a `accepted_model.glb`
- La promoción toma el objeto seleccionado en Blender.
- Exporta GLB usando `bpy.ops.export_scene.gltf(..., export_format="GLB")`.
- Guarda `accepted_manifest.json`.
- Actualiza `job_manifest.json` con `active_accepted_version`.
- No permite sobrescribir `accepted_model.glb` dentro de la misma versión sin nueva versión.
- Si existe `edited/edited_model.glb` y el objeto seleccionado fue guardado como `edited`, la promoción registra esa procedencia en `accepted_manifest.json`.

## `edited/edited_model.glb`
- Existe exportación explícita de `edited/edited_model.glb`.
- El botón del add-on es `Save Selected Object as Edited Model`.
- El core guarda `edited_manifest.json` junto con `edited_model.glb`.
- La promoción a accepted puede registrar `source_type=edited_model` o `source_type=selected_object`.

## Exportación a STL
- Está bloqueada si no existe `active_accepted_version`.
- Está bloqueada si no existe `accepted_model.glb`.
- Usa el objeto accepted cargado en Blender para exportar STL en la UI del add-on.
- En el core Python puede usar `trimesh` o un exporter inyectado.

## Validación STL
- Genera `stl_validation_report.json`.
- Genera `printability_report.json`.
- Si `trimesh` no puede validar, el estado queda en `validation_unavailable`.
- No se declara `print_ready_candidate` si no hay validación suficiente o si la malla no es watertight.

## Funciones del add-on
La UI principal ahora es por estados:
- `no_job`
- `job_created`
- `result_imported`
- `candidate_imported`
- `accepted_created`
- `stl_exported`

Superficie principal visible por estado:
- `no_job`: `Primary Image`, `Create Job Package`
- `job_created`: `Job ID`, `Open Job Folder`, `Cloud Worker`, `Result Package`, `Import Result Package`
- `result_imported`: `Candidate Path`, `Import Candidate GLB`
- `candidate_imported`: `Visual Score`, `Geometry Score`, `Usable as Base`, `Notes`, `Save Review`, `Use Selected Object as Accepted Model`
- `candidate_imported`: `Visual Score`, `Geometry Score`, `Usable as Base`, `Notes`, `Save Review`, `Save Selected Object as Edited Model`, `Use Selected Object as Accepted Model`
- `accepted_created`: `Accepted Model Path`, `Export STL from Accepted Model`, `Open Accepted Folder`
- `stl_exported`: `Accepted Model Path`, `Accepted STL Path`, `Open Accepted Folder`

Secciones colapsables:
- `Cloud Worker`: `Cloud Root Folder`, `Cloud Status`, `Cloud Result Path`, `Send Job to Cloud`, `Check Cloud Results`, `Import Cloud Result`, `Open Cloud Folder`
- `Advanced Input`: `Input Mode`, `Additional View`, `View Type`, `Prompt`, `Target Size`
- `Advanced Review`: `Object Similarity`, `Holes / Artifacts`, `Repair Needed`
- `Debug / Version Info`: `Job ID`, `Version ID`, `UI State`

Comportamiento del `Cloud Worker` en el add-on:
- `Send Job to Cloud` valida job activo, `job_package.zip`, `Cloud Root Folder` y crea carpetas cloud faltantes bajo la raíz existente.
- `Send Job to Cloud` crea o actualiza `cloud_status.json` dentro del job local.
- `Check Cloud Results` detecta `completed`, `processing`, `sent_to_cloud`, `failed` o `result_not_ready` sin bloquear Blender.
- `Import Cloud Result` usa el ZIP detectado en `completed/` y llama a la lógica existente de `Import Result Package`.
- `Open Cloud Folder` abre `Cloud Root Folder` si la ruta existe.

## Funciones externas pendientes
- Worker Kaggle real.
- Space de Hugging Face.
- Worker Modal.
- Integración de modificación IA desde `accepted_model.glb`.
- Comparación visual entre versiones.
- Carga de múltiples vistas en lista dinámica dentro del add-on.

## Cómo integrar Colab/Kaggle/Hugging Face/Modal en el futuro
### Colab/Kaggle
- Modo manual:
  - subir `job_package.zip`
  - ejecutar el notebook
  - descargar `result_package.zip`
- Modo Drive Worker:
  - montar Drive
  - procesar `incoming/*.zip`
  - escribir `completed/<job_id>_result_package.zip`
  - escribir `completed/<job_id>_status.json`

### Hugging Face
- Crear un worker o Space que reciba `job_package.zip`.
- Mantener el mismo contrato de salida con `model.glb` y `result_manifest.json`.
- No depender de tokens hardcodeados.

### Modal
- Crear función serverless GPU que monte el package, ejecute el motor y devuelva `result_package.zip`.
- Mantener el mismo contrato ZIP para no cambiar el add-on.

## PyTorch CPU probe aislado para TripoSR local
Razón de la prueba:
- Antes de instalar TripoSR local, se aisló una verificación mínima de PyTorch CPU para confirmar que el host puede importar `torch`, crear tensores y ejecutar una operación básica sin tocar el core HY3D ni el add-on limpio.
- La meta fue validar la base runtime de CPU, no declarar que TripoSR local CPU ya sea práctico o rápido en esta máquina.

Entorno aislado:
- raíz: `<external_engines_root>\\triposr-local`
- venv: `<external_engines_root>\\triposr-local\.venv`
- wrapper: `<repo>\\tools\\triposr\setup_pytorch_cpu_probe.ps1`
- probe runtime: `<external_engines_root>\\triposr-local\pytorch_probe.py`
- reporte: `<external_engines_root>\\triposr-local\pytorch_probe_report.json`

Variables configuradas en el wrapper:
- `HF_HOME=<external_engines_root>\cache\huggingface`
- `TRANSFORMERS_CACHE=<external_engines_root>\cache\huggingface`
- `TORCH_HOME=<external_engines_root>\cache\torch`
- `TMP=<external_engines_root>\tmp`
- `TEMP=<external_engines_root>\tmp`

Comandos usados:
1. ejecución del wrapper:
   - `powershell -File <repo>\\tools\\triposr\setup_pytorch_cpu_probe.ps1`
2. instalación de PyTorch CPU dentro del venv aislado:
   - `python -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu`

Resultado verificado del probe:
- `python_version = 3.11.9`
- `torch_version = 2.12.0+cpu`
- `cuda_available = false`
- `cuda_version = null`
- `tensor_test_ok = true`
- `tensor_test_seconds = 0.002697`

Decisión operativa:
- El probe sí habilitó una verificación separada de instalación de TripoSR local CPU, porque la base aislada de PyTorch CPU quedó funcional.
- No se debe interpretar este probe como prueba de viabilidad práctica de TripoSR local CPU; solo valida la capa mínima `python + torch + tensor op`.
- La decisión final no depende del probe solo, sino del setup real de TripoSR y de un smoke que produzca un `.glb`.

## TripoSR local CPU aislado: setup y smoke real
Razón del cambio temporal de enfoque:
- Hubo fricción operativa con el puente Colab/Drive para esta fase y se decidió medir primero si un modo local controlado era viable sin tocar el core HY3D ni el add-on limpio.
- La meta era estricta: generar un `.glb` real o detener la integración local si CPU-only no era práctico.

Entorno local usado:
- raíz del motor: `<external_engines_root>\\triposr-local`
- repositorio: `<external_engines_root>\\triposr-local\TripoSR`
- venv: `<external_engines_root>\\triposr-local\.venv`
- outputs: `<external_engines_root>\\triposr-local\outputs`
- wrapper setup: `<repo>\\tools\\triposr\setup_triposr_local.ps1`
- wrapper smoke: `<repo>\\tools\\triposr\test_triposr_local.ps1`
- primer input inválido: `<repo>\hy3d_v2\test_assets\sample_input.png`
- input real del smoke válido: `<repo>\hy3d_v2\test_assets\real_smoke_input.png`

Comandos usados:
1. setup aislado de TripoSR:
   - `powershell -File <repo>\\tools\\triposr\setup_triposr_local.ps1`
2. smoke local CPU:
   - `powershell -File <repo>\\tools\\triposr\test_triposr_local.ps1`
3. comando objetivo del smoke válido:
   - `python run.py <repo>\hy3d_v2\test_assets\real_smoke_input.png --output-dir <external_engines_root>\\triposr-local\outputs\smoke --device cpu --model-save-format glb`
4. fallback del smoke válido:
   - `python run.py <repo>\hy3d_v2\test_assets\real_smoke_input.png --output-dir <external_engines_root>\\triposr-local\outputs\smoke --device cpu`

Resultado del setup:
- `<external_engines_root>\\triposr-local\install_report.json` quedó con `success = true`.
- `python_version = 3.11.9`
- `torch_version = 2.12.0+cpu`
- `cuda_available = false`
- `install_started_at = 2026-05-21T10:45:40.9697261-05:00`
- `install_finished_at = 2026-05-21T10:47:59.5642125-05:00`
- duración real del setup: ~138.6 segundos
- El setup quedó sano solo cuando se aisló `torchmcubes` como instalación CPU separada y luego se fijaron dependencias compatibles para Windows CPU:
  - `numpy==1.26.4`
  - `rembg==2.0.69`
  - `onnxruntime`
  - `gradio==4.8.0`
- El repo `TripoSR` quedó instalado en `<external_engines_root>\\triposr-local\TripoSR` sin tocar `<repo>\hy3d_v2`.

Resultado del smoke:
- `<external_engines_root>\\triposr-local\smoke_report.json` quedó con:
  - `success = true`
  - `status = success`
  - `image_width = 512`
  - `image_height = 512`
  - `image_mode = RGB`
  - `output_glb = <external_engines_root>\\triposr-local\outputs\smoke\0\mesh.glb`
  - `output_obj = null`
  - `output_ply = null`
  - `duration_seconds = 329.007`
  - `local_cpu_practical = true`
- El primer smoke sí alcanzó `run.py`, descargó el checkpoint completo (`model.ckpt` de ~1.68 GB), inicializó el modelo y luego falló en `Processing images`.
- La causa real del primer fallo no fue el runtime base ni `torch`; fue el asset de entrada solicitado:
  - `<repo>\hy3d_v2\test_assets\sample_input.png`
  - tamaño real detectado: `RGB (1, 1)`
  - error real: `ValueError: tile cannot extend outside image`
- Luego se creó una imagen real válida para repetir la prueba:
  - origen: `<user_downloads>\C5.jpg`
  - copia operativa: `<repo>\hy3d_v2\test_assets\real_smoke_input.png`
  - dimensiones finales: `512x512`
  - modo: `RGB`
- Con esa imagen válida, TripoSR local CPU sí completó el pipeline de punta a punta y exportó `mesh.glb`.
- Duración real observada:
  - primer intento con descarga de pesos: `Initializing model finished in 871324.00ms` (~14.52 min)
  - primer rerun con imagen válida exportó `.obj` en el fallback y dejó evidencia de que la inferencia CPU era funcional:
    - `Running model finished in 115776.85ms`
    - `Extracting mesh finished in 142400.28ms`
    - `mesh.obj` generado
  - rerun limpio final con imagen válida y salida GLB:
    - `duration_seconds = 329.007`
    - `Running model finished in 82601.19ms`
    - `Extracting mesh` completó y la exportación final produjo `mesh.glb`

Decisión operativa final:
- No se declara `local_cpu_not_practical` en esta fase.
- TripoSR local CPU ya quedó validado como ruta funcional con imagen real válida y salida `GLB`.
- El siguiente paso correcto es completar `run_triposr_local.ps1` sobre esta base real, no detener la línea local.
- No se crea en esta fase el add-on nuevo `HY3D Local Connector`.
- No se toca `hy3d_v2_clean`.
- No se toca el core GLB/STL.

## Wrapper local: run_triposr_local.ps1
Objetivo de esta fase:
- Convertir una imagen local válida en un `result_package.zip` compatible con el importador real de HY3D, sin tocar el core, sin Colab, sin Cloud Worker y sin crear todavía `HY3D Local Connector`.

Archivo creado:
- `<repo>\\tools\\triposr\run_triposr_local.ps1`

Contrato de entrada:
- parámetros soportados:
  - `-input_image`
  - `-output_dir`
  - `-job_id`
  - `-version_id`
- validaciones:
  - archivo existente
  - extensiones permitidas: `.png`, `.jpg`, `.jpeg`, `.webp`, `.bmp`
  - dimensiones mínimas `128x128`

Comando de prueba real ejecutado:
- `powershell -ExecutionPolicy Bypass -File <repo>\\tools\\triposr\run_triposr_local.ps1 -input_image "<repo>\hy3d_v2\test_assets\real_smoke_input.png" -output_dir "<external_engines_root>\\triposr-local\outputs\job_test" -job_id "job_test" -version_id "v1"`

Resultado del wrapper:
- `run_report.json` quedó con:
  - `success = true`
  - `status = completed`
  - `duration_seconds = 73.04`
  - `local_cpu_practical = true`
  - `output_glb = <external_engines_root>\\triposr-local\outputs\job_test\engine_raw\0\mesh.glb`
  - `result_package = <external_engines_root>\\triposr-local\outputs\job_test\result_package.zip`
- `result_package.zip` sí existe en:
  - `<external_engines_root>\\triposr-local\outputs\job_test\result_package.zip`

Contenido real del paquete:
- `result_manifest.json`
- `model.glb`
- `engine_output/model.glb`
- `logs/engine_log.txt`

Observaciones de compatibilidad:
- El primer intento de importación del ZIP falló porque `result_manifest.json` se escribió con BOM UTF-8 y el importador limpio lo rechazó con:
  - `result_manifest.json is invalid: Unexpected UTF-8 BOM`
- Corrección aplicada:
  - `run_triposr_local.ps1` ahora escribe JSON sin BOM.
- Tras regenerar el ZIP, la importación fue exitosa.

Prueba real de importación en HY3D v2 Clean:
- Se validó con el helper real del add-on limpio:
  - `_import_result_package_into_session()`
- Workspace fallback usado:
  - `<repo>\hy3d_v2_clean_workspace`
- Job de prueba creado para importar:
  - `job_4c6e20a9043d`
- Candidate importado correctamente en:
  - `<repo>\hy3d_v2_clean_workspace\jobs\job_4c6e20a9043d\versions\v1\engine_output\model.glb`
- Conclusión:
  - el `result_package.zip` generado por `run_triposr_local.ps1` sí es importable por HY3D v2 Clean.

Pendientes inmediatos:
- No crear todavía `HY3D Local Connector`.
- No tocar `hy3d_v2_clean`.
- No tocar el core GLB/STL.
- La siguiente fase correcta sería cablear este wrapper como backend local aislado, solo si se mantiene la decisión de seguir con integración local.

Bitácora resumida:
1. `test_triposr_local.ps1` confirmó smoke real exitoso con `real_smoke_input.png`.
2. Se creó `run_triposr_local.ps1` con validación de imagen, ejecución CPU local, empaquetado y reportes.
3. El primer intento del wrapper produjo ZIP válido en estructura, pero `result_manifest.json` tenía BOM y no era importable.
4. Se corrigió la escritura JSON a UTF-8 sin BOM.
5. El segundo intento generó `result_package.zip` importable y dejó `run_report.json` con `success = true`.

## Pruebas realizadas
Pruebas automatizadas creadas:
- `test_create_job_and_package`
- `test_import_result_package_creates_candidate_manifest`
- `test_save_review_and_promote_to_accepted`
- `test_block_stl_without_accepted_model`
- `test_export_stl_uses_accepted_model_only`
- `test_create_second_version_from_active_accepted`
- `test_no_overwrite_same_version_accepted_glb`
- `test_model_glb_does_not_create_stl_without_accepted`
- `test_addon_does_not_expose_legacy_routes`
- `test_empty_path_does_not_resolve_to_dot`
- `test_import_candidate_blocked_without_result_package`
- `test_import_candidate_blocked_without_model_glb`
- `test_export_stl_blocked_without_accepted_model`
- `test_import_result_requires_zip_file`
- `test_ui_disables_candidate_import_without_candidate`
- `test_save_edited_model_and_promote_from_edited`
- `test_import_result_package_rejects_missing_result_manifest`
- `test_import_result_package_rejects_unsafe_zip_paths`
- `test_send_job_to_cloud_copies_zip_and_creates_status`
- `test_check_cloud_results_detects_completed_package`
- `test_check_cloud_results_not_ready`
- `test_check_cloud_results_detects_failed_error`
- `test_cloud_root_empty_is_not_treated_as_dot`
- `test_cloud_folders_are_created_if_missing`
- `test_cloud_file_names_follow_contract`
- `test_import_cloud_result_reuses_import_result_package_operator`
- `test_clean_addon_has_unique_bl_info`
- `test_clean_addon_no_legacy_operator_ids`
- `test_select_primary_image_accepts_valid_image`
- `test_select_primary_image_rejects_empty_path`
- `test_select_primary_image_rejects_invalid_extension`
- `test_send_job_to_cloud_copies_job_package_and_creates_status`
- `test_check_cloud_results_detects_completed`
- `test_check_cloud_results_detects_failed`
- `test_check_cloud_results_not_ready`
- `test_import_cloud_result_reuses_import_result_package`

Cobertura funcional de Fase 1:
- crear job
- crear `job_package.zip`
- importar `result_package_sample.zip`
- detectar `model.glb`
- guardar `candidate_manifest.json`
- guardar `manual_review.json`
- promover a `accepted_model.glb`
- bloquear STL sin accepted
- exportar STL desde accepted
- manejar `v1` y `v2`
- validar manifiesto multi-imagen
- evitar STL desde `model.glb`
- evitar sobrescritura de accepted
- verificar ausencia de UI legacy en el add-on
- validar `Select Primary Image`
- validar `Cloud Worker` del add-on limpio
- validar que `Import Cloud Result` reuse el importador del core

Resultado actual de pruebas automatizadas:
- `pytest -q hy3d_v2/tests` -> `47 passed in 5.39s`

Prueba aislada adicional fuera del repo HY3D:
- Wrapper ejecutado: `<repo>\\tools\\triposr\setup_pytorch_cpu_probe.ps1`
- Reporte generado: `<external_engines_root>\\triposr-local\pytorch_probe_report.json`
- Resultado:
  - `cuda_available = false`
  - `tensor_test_ok = true`
  - `tensor_test_seconds = 0.002697`
- Esta prueba no instaló TripoSR y no tocó `<repo>\hy3d_v2`.

Assets de prueba reales creados:
- `test_assets/sample_input.png`
- `test_assets/sample_model.glb`
- `test_assets/result_package_sample.zip`

Smoke real ejecutado en Blender 4.2:
1. instalar add-on desde `dist/hy3d_v2_addon.zip`
2. crear job desde `sample_input.png`
3. importar `result_package_sample.zip`
4. importar `model.glb`
5. mover el objeto importado
6. guardar review
7. promover a `accepted_model.glb`
8. exportar `accepted_model.stl`

Evidencia del smoke:
- `SMOKE_JOB_ID= job_eddd878afc22`
- `SMOKE_ACCEPTED_GLB= <blender_user_data>\4.2\datafiles\hy3d_v2_workspace\jobs\job_eddd878afc22\versions\v1\accepted\accepted_model.glb`
- `SMOKE_ACCEPTED_STL= <blender_user_data>\4.2\datafiles\hy3d_v2_workspace\jobs\job_eddd878afc22\versions\v1\accepted\accepted_model.stl`

Smoke reforzado con `edited_model.glb`:
1. crear job
2. importar `result_package_sample.zip`
3. importar candidate GLB
4. guardar review
5. `Save Selected Object as Edited Model`
6. `Use Selected Object as Accepted Model`
7. `Export STL from Accepted Model`

Estado honesto del smoke reforzado:
- `Create Job Package`, `Import Result Package`, `Import Candidate GLB`, `Save Review`, `Save Selected Object as Edited Model` y `Use Selected Object as Accepted Model` sí se ejecutaron en Blender 4.2.
- `Export STL from Accepted Model` sigue fallando en smoke headless/background con el mensaje `Load or accept an object in Blender before STL export`.
- No hay ejecutable local de Blender 5.1 disponible en esta máquina para repetir el smoke solicitado en esa versión.

## Errores encontrados
- `pytest` no encontraba el paquete `hy3d_v2` durante la primera recolección. Se corrigió agregando `tests/conftest.py`.
- La validación opcional depende del stack local. Si `trimesh` o `pyvista` no están listos, el sistema degrada honestamente en lugar de declarar éxito falso.
- El primer ZIP `<repo>\hy3d_v2_addon.zip` no era aceptado por Blender como módulo válido en instalación manual. La evidencia del usuario fue `Modules Installed ()`.
- Causa corregida: el entrypoint raíz no exponía `bl_info` de forma explícita y el empaquetado no estaba controlado por un script reproducible mínimo.
- Corrección aplicada: `hy3d_v2/__init__.py` ahora declara `bl_info` directamente y delega `register`/`unregister` a `blender_addon`; además se creó `scripts/package_blender_addon.py` para producir un ZIP limpio con solo el contenido runtime del add-on.
- Verificación realizada: Blender 4.2 en modo background instaló `<repo>\dist\hy3d_v2_addon.zip` y reportó `HY3D_MATCHES= [('hy3d_v2', 'HY3D v2')]`.
- El siguiente fallo real ya no era de empaquetado sino de rutas vacías en la UI. La evidencia fue `[Errno 13] Permission denied: '.'`, `RuntimeError: Error: Please select a file` y `accepted_model_path = ""`.
- Causa corregida: el add-on convertía cadenas vacías en `Path('.')` y permitía ejecutar operadores con rutas inválidas para candidato, accepted y result package.
- Corrección aplicada: el add-on ahora usa helpers centrales `_resolve_existing_file(...)` y `_resolve_existing_dir(...)` para impedir que rutas vacías o inválidas se conviertan en `"."`; además se bloquean operadores y acciones de UI cuando no existe una ruta válida.
- En Blender 5.1 apareció otro fallo real: `Calling operator "bpy.ops.export_mesh.stl" error, could not be found`.
- Causa corregida: el add-on asumía `bpy.ops.export_mesh.stl`, pero esa ruta no es estable entre versiones de Blender.
- Corrección aplicada: la exportación STL del add-on ahora usa `bpy.ops.wm.stl_export` como ruta principal y mantiene fallback controlado solo si existe `export_mesh.stl`.
- El fallo persistente de permisos no estaba en el GLB de muestra sino en el workspace del add-on.
- Causa corregida: el add-on estaba escribiendo jobs dentro del árbol instalado; ahora usa `bpy.utils.user_resource(.../hy3d_v2_workspace)` como workspace local.
- La UI anterior mostraba demasiadas acciones a la vez y permitía una navegación poco guiada del flujo.
- Corrección aplicada: la UI principal ahora se renderiza por estado del job y muestra solo la siguiente acción necesaria.
- `import_result_package()` era todavía laxo respecto al contrato del ZIP.
- Corrección aplicada: ahora valida `result_manifest.json`, rechaza ZIP sin `model.glb` y bloquea rutas inseguras dentro del paquete.
- El smoke reforzado con `edited_model.glb` dejó un gap real en runtime: `Export STL from Accepted Model` todavía falla en Blender background 4.2 con `Load or accept an object in Blender before STL export`.
- El notebook previo de Colab era solo placeholder y no garantizaba devolver un `result_package.zip` importable por el add-on sin ajustes manuales.
- Corrección aplicada: `notebooks/HY3D_worker_colab.ipynb` ahora genera un `result_package.zip` alineado al contrato real de `import_result_package()`, incluyendo `result_manifest.json` y `model.glb` en la raíz del ZIP, además de `engine_output/model.glb` y `logs/engine_log.txt`.
- Límite actual: el notebook quedó validado como archivo `.ipynb` y con contrato coherente, pero no fue ejecutado de punta a punta en Colab durante esta sesión.
- Faltaba el puente seguro entre Blender y un worker manual por Google Drive sin tocar el core local.
- Corrección aplicada: el add-on ahora implementa `Send Job to Cloud`, `Check Cloud Results`, `Import Cloud Result` y `Open Cloud Folder`, con `cloud_status.json` local y detección segura de `incoming/completed/failed`.
- Límite actual: la integración quedó probada por tests de filesystem y contrato, pero no fue ejecutada de punta a punta en Blender 5.1 + Google Drive + Colab durante esta sesión.
- Persistía un fallo reportado en Blender 5.1 durante `Create Job Package`: `RuntimeError: Error: Please select a file` y `[Errno 13] Permission denied: '.'`.
- Auditoría realizada sobre el add-on instalado real en `<blender_user_data>\5.1\scripts\addons\hy3d_v2\blender_addon\__init__.py`: la línea 191 actual ya no corresponde a `bpy.ops.import_scene.gltf(...)`; hoy contiene el loop de validación de `additional_view_path`. Esto indica que el traceback previo no describe la build actualmente instalada.
- Corrección aplicada: se agregó `ADDON_BUILD_ID = hy3d_v2_20260520_1155_routesafe`, visible en UI y en consola al registrar el add-on.
- Corrección aplicada: se agregó `HY3D Self Check` para imprimir ruta real del add-on cargado, build, workspace, `primary_image_path`, `job_id`, `job_package_path`, `result_package_path`, `candidate_model_path` y `accepted_model_path`.
- Corrección aplicada: `Create Job Package` ahora valida de forma estricta `primary_image_path` antes de llamar al core y rechaza `""`, `"."`, rutas inexistentes, directorios y extensiones no permitidas con mensajes explícitos.
- Corrección aplicada: se agregó `Reset HY3D Session` para limpiar solo el estado de UI sin borrar archivos del job.
- Corrección aplicada: se agregó `Use Sample Input`, apuntando primero a `<repo>\hy3d_v2\test_assets\sample_input.png`.
- Verificación con `bpy` real en Blender 4.2: `HY3D Self Check` y `Use Sample Input -> Create Job Package` funcionan con la build nueva.
- Límite actual: no existe `<path_to_blender_executable>` 5.1 accesible en esta máquina, por lo que no se pudo verificar visualmente la UI ni ejecutar el smoke con `bpy` real en 5.1 durante esta sesión.
- Dado que Blender 5.1 seguía mostrando comportamiento inconsistente con el add-on `hy3d_v2`, se creó un add-on nuevo y limpio `hy3d_v2_clean`, con paquete, panel, operadores y workspace distintos.
- El add-on limpio no reutiliza `bl_idname` ni `Panel ID` del add-on anterior y no depende del estado previo de `hy3d_v2` dentro de Blender.
- Build previa funcional del add-on limpio: `hy3d_v2_clean_20260520_1230`.
- Build actual del add-on limpio con Cloud Worker: `hy3d_v2_clean_20260521_1535_cloud`.
- Primer smoke real del add-on limpio en Blender 4.2: exitoso de punta a punta sin traceback en el flujo local mínimo.
- Estado Blender 5.1 del add-on limpio: el árbol `<blender_user_data>\5.1\scripts\addons\hy3d_v2_clean` fue instalado y el ZIP contiene la estructura correcta, pero no se pudo ejecutar Blender 5.1 en esta máquina para verificar la UI o el flujo con `bpy` real.
- La sesión anterior había dejado `hy3d_v2_clean/__init__.py` a medio integrar para Cloud Worker.
- Corrección aplicada: se terminó la integración limpia con propiedades, helpers, operadores y UI simple para `Select Primary Image`, `Send Job to Cloud`, `Check Cloud Results`, `Import Cloud Result` y `Open Cloud Folder`.
- Error corregido durante esta sesión: `send_job_to_cloud()` y `check_cloud_results()` validaban el job contra `workspace_root()` global en vez del `root` recibido; ahora usan la raíz explícita y son testeables fuera de Blender.
- Estado honesto actual: la capa Cloud Worker del add-on limpio quedó verificada por pruebas de filesystem y contrato, no por un smoke real Blender 5.1 -> Drive -> Colab -> Blender.
- Antes de instalar TripoSR local nuevo, se ejecutó un probe aislado de PyTorch CPU en `<external_engines_root>\\triposr-local`.
- El primer intento del wrapper falló por interpolación inválida de `${LASTEXITCODE}` dentro de una cadena PowerShell; se corrigió en el propio wrapper.
- El segundo intento del wrapper falló por invocación ambigua del ejecutable base de Python desde un array PowerShell; se corrigió devolviendo `Executable` y `PrefixArgs` de forma explícita.
- Resultado final del probe: `torch 2.12.0+cpu` importó correctamente, `cuda_available = false` y `tensor_test_ok = true`.
- Cambio temporal de enfoque confirmado: no se seguirá empujando Colab/Drive en esta fase y se auditó una ruta local controlada para TripoSR antes de tocar Blender.
- Resultado real del setup local final: `setup_triposr_local.ps1` sí completó la instalación aislada con `success = true`, `torch 2.12.0+cpu` y `cuda_available = false`.
- Resultado real del smoke local final: `test_triposr_local.ps1` primero descartó el asset `1x1`, luego repitió el smoke con `real_smoke_input.png` (`512x512`, `RGB`) y produjo `mesh.glb` en `<external_engines_root>\\triposr-local\outputs\smoke\0\mesh.glb`.
- Resultado real del wrapper local final: `run_triposr_local.ps1` generó `<external_engines_root>\\triposr-local\outputs\job_test\result_package.zip` y ese ZIP fue importable por HY3D v2 Clean en el workspace fallback.
- Decisión de fase: no construir todavía `HY3D Local Connector`, pero sí continuar después con integración local porque ya existe una base real funcional en CPU local con smoke y package importable.

## Pendientes
- Mejorar validación multi-imagen con heurísticas de UI/captura de pantalla.
- Soportar más de una vista adicional desde la UI.
- Agregar botón futuro `Generate New Version from Accepted`.
- Verificar el mismo smoke real en Blender 5.1 con el ZIP actual.
- Resolver el gap del operador STL cuando el smoke corre en Blender background/headless.
- Ejecutar smoke real del add-on limpio con imagen real en Blender 5.1:
  - `Select Primary Image`
  - `Create Job Package`
- Ejecutar smoke real del puente Google Drive:
  - `Send Job to Cloud`
  - worker en Colab con runtime GPU
  - `Check Cloud Results`
  - `Import Cloud Result`
- Si en una fase futura se reabre la vía local:
  - resolver una estrategia determinística CPU-only para `torchmcubes` en Windows o reemplazar esa dependencia
  - completar un setup que deje `rembg` y el resto del runtime realmente instalados
  - repetir smoke y exigir producción real de `.glb` antes de crear cualquier add-on conector
- Verificar la build `hy3d_v2_20260520_1155_routesafe` directamente en Blender 5.1 con UI visible y repetir:
  - `HY3D Self Check`
  - `Use Sample Input`
  - `Create Job Package`
- Verificar en Blender 5.1 el add-on limpio `hy3d_v2_clean` con este orden exacto:
  - `Self Check`
  - `Reset Session`
  - `Use Sample Input`
  - `Create Job Package`
  - `Import Sample Result Package`
  - `Import Candidate GLB`
  - `Save Basic Review`
  - `Accept Selected Object`
  - `Export STL From Accepted`

## Estado actual verificable
### Funcionando
- Estructura base del proyecto.
- Documento maestro único.
- Creación de job local.
- Packaging de `job_package.zip`.
- Importación de `result_package_sample.zip`.
- Generación de `candidate_manifest.json`.
- Guardado de `manual_review.json`.
- Promoción a `accepted_model.glb`.
- Bloqueo de STL si no hay accepted activo.
- Exportación de STL desde la versión accepted activa.
- Estructura preparada para `v2` desde `accepted_model.glb`.
- Add-on sin strings o rutas legacy en su superficie actual.
- Empaquetado reproducible del add-on mediante `hy3d_v2/scripts/package_blender_addon.py`.
- ZIP runtime limpio en `<repo>\dist\hy3d_v2_addon.zip`.
- Detección del add-on por Blender 4.2 como módulo `hy3d_v2` con nombre visible `HY3D v2`.
- Validación común de rutas en el add-on para evitar tratar `""` como `Path('.')`.
- Validación central `_resolve_existing_file/_resolve_existing_dir` para impedir que rutas vacías terminen como `"."`.
- `Import Candidate GLB` bloqueado si no existe un `.glb` candidato válido.
- `Import Result Package` bloqueado si no existe un `.zip` válido.
- `Export STL from Accepted Model` bloqueado si no existe un `.glb` accepted válido.
- La UI deshabilita `Import Candidate GLB` y `Export STL from Accepted Model` cuando sus rutas aún no son válidas.
- La UI muestra claramente `Result Package Path`, `Candidate Path` y `Accepted Model Path`.
- `Import Candidate GLB` sigue deshabilitado justo después de `Create Job Package` y solo se habilita tras un `Import Result Package` exitoso.
- Pruebas nuevas de rutas y bloqueo previo ejecutadas y pasando.
- Al crear un job nuevo se limpian rutas de sesión heredadas para evitar candidato/accepted obsoletos en la UI.
- Al importar un nuevo `result_package.zip`, el add-on limpia `accepted_model_path` anterior para no mezclar versiones o estados viejos.
- La exportación STL del add-on ya tiene compatibilidad explícita con operadores modernos de Blender.
- Existe exportación explícita de `edited/edited_model.glb` y `edited_manifest.json`.
- `accepted_manifest.json` ahora puede registrar `source_type=selected_object` o `source_type=edited_model`.
- `import_result_package()` valida `result_manifest.json`, `engine_output/model.glb` y bloquea entradas ZIP inseguras.
- `candidate_validation_report.json` ahora incluye `file_size`, `vertex_count`, `face_count`, `bbox`, `component_count`, `readable_by_trimesh` y `validation_warnings`.
- `stl_validation_report.json` ahora expone `watertight`, `manifold`, `component_count`, `bbox`, `non_manifold_edges` y `printability_status`.
- La UI principal del add-on ya no muestra todas las acciones a la vez: se presenta por estado (`no_job`, `job_created`, `result_imported`, `candidate_imported`, `accepted_created`, `stl_exported`).
- `Version ID` ya no está en la UI principal; solo aparece en `Debug / Version Info`.
- `Advanced Input` y `Advanced Review` quedaron fuera del flujo principal como secciones colapsables.
- `sample_model.glb` es un GLB real exportado desde Blender, no bytes dummy.
- `result_package_sample.zip` existe y se usa en pruebas automatizadas.
- El flujo local completo ya fue ejecutado con éxito en Blender 4.2 usando el add-on empaquetado y los `test_assets`.
- El workspace de jobs del add-on está fuera de la carpeta instalada y se crea bajo los datos de usuario de Blender.
- El notebook `notebooks/HY3D_worker_colab.ipynb` ya implementa el worker manual de Fase 2 para producir `result_package.zip` desde `job_package.zip` usando TripoSR Clean.
- El contrato de salida del notebook ya está alineado con `import_result_package()` sin requerir cambios en el core o en el add-on.
- El add-on puede copiar `job_package.zip` a `incoming/<job_id>_job_package.zip` bajo una raíz Drive existente.
- El add-on crea `cloud_status.json` local con `status`, nombres esperados y timestamps.
- `Check Cloud Results` detecta `completed/<job_id>_result_package.zip`, estados de `processing`, ausencia temporal de resultados y fallos en `failed/`.
- `Import Cloud Result` reutiliza la lógica actual de `Import Result Package`.
- Las carpetas cloud faltantes bajo una raíz válida se crean automáticamente: `incoming`, `processing`, `completed`, `failed`, `logs`, `notebooks`.
- El notebook implementa modo manual y modo Drive Worker sin cambiar el contrato local de candidato/accepted/STL.
- El add-on actualizado fue reempaquetado en `<repo>\dist\hy3d_v2_addon.zip`.
- `ADDON_BUILD_ID = hy3d_v2_20260520_1155_routesafe` existe y se imprime al registrar el add-on.
- La UI del add-on ahora muestra `HY3D v2 Build: hy3d_v2_20260520_1155_routesafe`.
- `HY3D Self Check` existe y reporta el estado runtime del add-on.
- `Reset HY3D Session` existe y limpia el estado de UI.
- `Use Sample Input` existe y selecciona `<repo>\hy3d_v2\test_assets\sample_input.png` si el archivo está presente.
- `Create Job Package` ahora valida estrictamente `primary_image_path` antes de llamar al core.
- El add-on instalado en `<blender_user_data>\5.1\scripts\addons\hy3d_v2\blender_addon\__init__.py` contiene la build `hy3d_v2_20260520_1155_routesafe`.
- Verificación con Blender 4.2 y `bpy` real:
  - `Self Check` imprimió la ruta cargada `<blender_user_data>\4.2\scripts\addons\hy3d_v2\blender_addon\__init__.py`
  - `Self Check` imprimió `workspace_root = <blender_user_data>\4.2\datafiles\hy3d_v2_workspace`
  - `Use Sample Input` terminó en `FINISHED`
  - `Create Job Package` terminó en `FINISHED`
  - `job_id = job_1865dccc27f0`
  - `job_package_path = <blender_user_data>\4.2\datafiles\hy3d_v2_workspace\jobs\job_1865dccc27f0\job_package.zip`
- Existe un add-on nuevo y aislado en `<repo>\hy3d_v2_clean_addon\hy3d_v2_clean\`.
- Existe un artefacto instalable limpio en `<repo>\dist\hy3d_v2_clean_addon.zip`.
- El ZIP limpio contiene raíz `hy3d_v2_clean/` y un `hy3d_core` vendorized dentro del paquete, sin tests ni docs.
- El add-on limpio usa workspace separado:
  - `bpy.utils.user_resource("DATAFILES", path="hy3d_v2_clean_workspace", create=True)`
- Existe un entorno externo aislado para probe PyTorch CPU:
  - `<external_engines_root>\\triposr-local`
  - `<external_engines_root>\\triposr-local\.venv`
  - `<external_engines_root>\\triposr-local\pytorch_probe_report.json`
- El probe aislado confirmó:
  - `cuda_available = false`
  - `tensor_test_ok = true`
- Existen wrappers aislados para evaluar TripoSR local sin tocar el core ni los add-ons activos:
  - `<repo>\\tools\\triposr\setup_pytorch_cpu_probe.ps1`
  - `<repo>\\tools\\triposr\setup_triposr_local.ps1`
  - `<repo>\\tools\\triposr\test_triposr_local.ps1`
- El add-on limpio es la interfaz oficial de Blender para HY3D v2.
- El add-on viejo `hy3d_v2` queda deprecated para uso interactivo en Blender.
- El add-on limpio expone la UI simple en este orden:
  - `Self Check`
  - `Reset Session`
  - `Select Primary Image`
  - `Use Sample Input`
  - `Create Job Package`
  - `Cloud Root Folder`
  - `Cloud Status`
  - `Send Job to Cloud`
  - `Check Cloud Results`
  - `Import Cloud Result`
  - `Open Cloud Folder`
  - `Import Sample Result Package`
  - `Import Candidate GLB`
  - `Save Basic Review`
  - `Accept Selected Object`
  - `Export STL From Accepted`
  - `Open Workspace Folder`
- `Self Check` del add-on limpio imprime:
  - `build_id`
  - `__file__`
  - `workspace`
  - `sample_input_exists`
  - `sample_result_package_exists`
  - `job_id`
  - `job_package_path`
  - `cloud_root_folder`
  - `cloud_status`
  - `cloud_result_package_path`
  - `candidate_model_path`
  - `accepted_model_path`
- Smoke completo del add-on limpio en Blender 4.2 y `bpy` real:
  - módulo detectado: `hy3d_v2_clean`
  - build cargada: `hy3d_v2_clean_20260520_1230`
  - `Self Check` ejecutado sin traceback
  - `Reset Session` -> `FINISHED`
  - `Use Sample Input` -> `FINISHED`
  - `Create Job Package` -> `FINISHED`
  - `Import Sample Result Package` -> `FINISHED`
  - `Import Candidate GLB` -> `FINISHED`
  - `Save Basic Review` -> `FINISHED`
  - `Accept Selected Object` -> `FINISHED`
  - `Export STL From Accepted` -> `FINISHED`
  - `job_id = job_d03392184a37`
  - `job_package_path = <blender_user_data>\4.2\datafiles\hy3d_v2_clean_workspace\jobs\job_d03392184a37\job_package.zip`
  - `accepted_model_path = <blender_user_data>\4.2\datafiles\hy3d_v2_clean_workspace\jobs\job_d03392184a37\versions\v1\accepted\accepted_model.glb`

### Parcialmente implementado
- Validación geométrica: ligera y dependiente de librerías opcionales.
- Multi-view: estructural y de packaging, no reconstrucción real.
- Versionado avanzado en UI: preparado solo como placeholder.
- Notebook externo: implementado para TripoSR Clean, pero sin verificación runtime completa en Colab durante esta sesión.
- Cloud bridge: implementado en add-on y notebook, pero sin smoke real completo contra Google Drive y Blender 5.1 durante esta sesión.
- Verificación Blender 5.1: el árbol instalado fue actualizado y auditado, pero no se pudo ejecutar `bpy` real en 5.1 porque el ejecutable no está disponible en esta máquina.
- Add-on limpio `hy3d_v2_clean`: empaquetado e instalado en el árbol 5.1, pero sin ejecución real en Blender 5.1 durante esta sesión.
- TripoSR local CPU: solo quedó evaluado como experimento aislado de entorno; no llegó a una integración usable ni a generación confirmada de GLB.

### Aún no probado
- Smoke real completo en Blender 5.1.
- Cierre exitoso del paso `Export STL from Accepted Model` dentro de smoke headless/background.
- Ejecución real de `HY3D_worker_colab.ipynb` en Colab con un `job_package.zip` del add-on y reimportación posterior del `result_package.zip` resultante.
- Flujo real `Send Job to Cloud` -> `Check Cloud Results` -> `Import Cloud Result` con Google Drive sincronizado en Windows.
- Worker real en Kaggle, Hugging Face o Modal.
- Smoke completo del add-on limpio en Blender 5.1 con UI visible y selección manual del objeto candidato.

## Artefacto instalable actual
- ZIP del add-on: `<repo>\dist\hy3d_v2_addon.zip`
- Punto de entrada Blender: `hy3d_v2/__init__.py`
- El paquete incluye el core necesario para que el add-on no dependa de un backend separado.
- ZIP del add-on limpio: `<repo>\dist\hy3d_v2_clean_addon.zip`
- Punto de entrada Blender del add-on limpio: `hy3d_v2_clean/__init__.py`
- Build actual del add-on limpio empaquetado: `hy3d_v2_clean_20260521_1535_cloud`

## Bitácora de implementación
### 2026-05-19
- Archivo: `hy3d_v2/hy3d_core/job_service.py`
  Motivo: creación del flujo central de jobs, packaging, importación de candidatos, revisión, aceptación, versionado y STL.
- Archivo: `hy3d_v2/hy3d_core/validation/service.py`
  Motivo: validación ligera del candidato con degradación honesta si faltan dependencias opcionales.
- Archivo: `hy3d_v2/hy3d_core/stl/service.py`
  Motivo: exportación y validación STL separadas del candidato GLB.
- Archivo: `hy3d_v2/blender_addon/__init__.py`
  Motivo: panel MVP de Blender y operadores conectados al core nuevo.
- Archivo: `hy3d_v2/scripts/create_job_package.py`
  Motivo: CLI para crear job y package desde fuera de Blender.
- Archivo: `hy3d_v2/scripts/create_result_package.py`
  Motivo: empaquetado reusable de `result_package.zip`.
- Archivo: `hy3d_v2/scripts/import_result_package.py`
  Motivo: importación reusable del package de resultado.
- Archivo: `hy3d_v2/scripts/validate_candidate.py`
  Motivo: ejecución manual de validación de candidatos.
- Archivo: `hy3d_v2/scripts/export_stl.py`
  Motivo: exportación CLI del STL desde la versión aceptada activa.
- Archivo: `hy3d_v2/notebooks/HY3D_worker_colab.ipynb`
  Motivo: implementación del worker manual de Fase 2 en Colab con TripoSR Clean, lectura de `job_package.zip`, generación de GLB y empaquetado de `result_package.zip` compatible con el importador local actual.
- Archivo: `hy3d_v2/config/external_engines.example.json`
  Motivo: contrato base para futuros motores externos.
- Archivo: `hy3d_v2/tests/test_phase1_flow.py`
  Motivo: pruebas funcionales del flujo mínimo de Fase 1.
- Archivo: `hy3d_v2/tests/test_addon_contract.py`
  Motivo: prueba de contrato para evitar superficie legacy en el add-on.
- Archivo: `hy3d_v2/tests/conftest.py`
  Motivo: corregir importación del paquete durante `pytest`.
- Archivo: `hy3d_v2/__init__.py`
  Motivo: exponer `bl_info`, `register` y `unregister` para instalación del add-on como paquete.
- Archivo: `<repo>\hy3d_v2_addon.zip`
  Motivo: artefacto instalable del add-on para Blender empaquetado desde el paquete `hy3d_v2`.
### 2026-05-20
- Archivo: `hy3d_v2/blender_addon/__init__.py`
  Motivo: agregar puente semiautomático por Google Drive con `Send Job to Cloud`, `Check Cloud Results`, `Import Cloud Result`, `Open Cloud Folder`, `cloud_status.json` y validación segura de rutas cloud.
- Archivo: `hy3d_v2/notebooks/HY3D_worker_colab.ipynb`
  Motivo: consolidar modo manual y modo Drive Worker con `drive.mount`, contrato `incoming/processing/completed/failed/logs`, empaquetado de `result_package.zip` y registro de errores auditables.
- Archivo: `hy3d_v2/tests/test_cloud_worker.py`
  Motivo: validar copia de ZIP a `incoming`, creación de `cloud_status.json`, detección de `completed`, tolerancia a resultado ausente, detección de `failed`, creación de carpetas cloud y contrato de nombres.
- Archivo: `hy3d_v2/tests/test_addon_contract.py`
  Motivo: verificar que `Import Cloud Result` reutiliza la lógica de `Import Result Package` en lugar de duplicarla.
- Archivo: `<repo>\dist\hy3d_v2_addon.zip`
  Motivo: regeneración del add-on empaquetado después de la capa Google Drive.
- Archivo: `hy3d_v2/blender_addon/__init__.py`
  Motivo: agregar `ADDON_BUILD_ID`, `HY3D Self Check`, `Reset HY3D Session`, `Use Sample Input`, `job_package_path` y validación estricta de `primary_image_path` antes de `Create Job Package`.
- Archivo: `hy3d_v2/tests/test_path_validation.py`
  Motivo: cubrir bloqueo de `Create Job Package` sin imagen primaria, rechazo de `"."`, rechazo de directorio como imagen, aceptación de imagen válida y verificación del build/self-check.
- Archivo: `hy3d_v2/tests/test_addon_contract.py`
  Motivo: verificar que el `Build ID` quede visible en la UI fuente del add-on.
- Archivo: `<repo>\dist\hy3d_v2_addon.zip`
  Motivo: regeneración del add-on con la build `hy3d_v2_20260520_1155_routesafe`.
- Archivo instalado auditado: `<blender_user_data>\5.1\scripts\addons\hy3d_v2\blender_addon\__init__.py`
  Motivo: confirmar que la build nueva sí quedó instalada en el árbol real de Blender 5.1.
- Archivo: `hy3d_v2/__init__.py`
  Motivo: hacer explícito `bl_info` en el entrypoint raíz y delegar `register`/`unregister` al submódulo del add-on para compatibilidad con el escáner de Blender.
- Archivo: `hy3d_v2/scripts/package_blender_addon.py`
  Motivo: crear empaquetado reproducible y mínimo del add-on sin carpeta superior extra ni archivos de prueba/documentación dentro del ZIP runtime.
- Archivo: `<repo>\dist\hy3d_v2_addon.zip`
  Motivo: nuevo artefacto instalable verificado por Blender 4.2 como módulo `hy3d_v2` con nombre visible `HY3D v2`.
- Archivo: `hy3d_v2/blender_addon/__init__.py`
  Motivo: agregar validación común de rutas, bloquear operadores con rutas vacías o inválidas y deshabilitar acciones de UI cuando aún no existe un candidato o accepted válido.
- Archivo: `hy3d_v2/hy3d_core/job_service.py`
  Motivo: endurecer validación de workspace y exigir `.zip` válido en la importación de `result_package.zip`.
- Archivo: `hy3d_v2/tests/test_path_validation.py`
  Motivo: cubrir los casos de `""` y `"."`, bloqueo de importación de candidato, bloqueo de exportación STL sin accepted y rechazo de result package inválido.
- Archivo: `hy3d_v2/blender_addon/__init__.py`
  Motivo: limpiar rutas de sesión al crear jobs o importar nuevos resultados y corregir compatibilidad de exportación STL para Blender 5.x mediante `wm.stl_export`.
- Archivo: `<repo>\dist\hy3d_v2_addon.zip`
  Motivo: nuevo paquete regenerado después de corregir el manejo de rutas heredadas y la exportación STL dependiente de versión.
- Archivo: `hy3d_v2/test_assets/sample_input.png`
  Motivo: asset de entrada local para demostrar el flujo mínimo sin IA externa.
- Archivo: `hy3d_v2/test_assets/sample_model.glb`
  Motivo: GLB real exportado desde Blender para reemplazar los candidatos dummy de pruebas.
- Archivo: `hy3d_v2/test_assets/result_package_sample.zip`
  Motivo: paquete de resultado local reusable para demostrar importación de candidato sin worker externo.
- Archivo: `hy3d_v2/tests/test_phase1_flow.py`
  Motivo: sustituir bytes dummy por assets reales y agregar verificación explícita de que `model.glb` no produce STL sin accepted.
- Archivo: `hy3d_v2/blender_addon/__init__.py`
  Motivo: reducir la superficie visible del add-on al flujo mínimo inmediato y mover el workspace a los datos de usuario de Blender.
- Archivo: `hy3d_v2/blender_addon/__init__.py`
  Motivo: centralizar la resolución segura de rutas con `_resolve_existing_file/_resolve_existing_dir` y bloquear operadores antes de que Blender intente abrir `"."` como archivo.
- Archivo: `hy3d_v2/tests/test_path_validation.py`
  Motivo: agregar la batería específica contra rutas vacías, candidato ausente, ZIP inválido y estado de UI antes de importar un candidato.
- Archivo: `hy3d_v2/blender_addon/__init__.py`
  Motivo: simplificar la interfaz a una UI por estados, mover opciones secundarias a `Advanced Input` y `Advanced Review`, y dejar `Version ID` solo en `Debug / Version Info`.
- Archivo: `hy3d_v2/hy3d_core/job_service.py`
  Motivo: endurecer `import_result_package()`, agregar extracción segura del ZIP y registrar/exportar `edited/edited_model.glb`.
- Archivo: `hy3d_v2/hy3d_core/validation/service.py`
  Motivo: enriquecer `candidate_validation_report.json` con tamaño de archivo, conteos y advertencias explícitas.
- Archivo: `hy3d_v2/hy3d_core/stl/service.py`
  Motivo: enriquecer `stl_validation_report.json` con `bbox`, `component_count`, `non_manifold_edges` y `printability_status`.
- Archivo: `hy3d_v2/tests/test_phase1_flow.py`
  Motivo: agregar cobertura de `edited_model.glb`, promoción desde edited y rechazo de ZIPs inseguros o incompletos.
- Archivo: `hy3d_v2/scripts/create_result_package.py`, `create_job_package.py`, `import_result_package.py`, `validate_candidate.py`, `export_stl.py`
  Motivo: permitir ejecución directa desde CLI resolviendo el paquete `hy3d_v2` sin depender del contexto de importación.
- Archivo: `<repo>\dist\hy3d_v2_addon.zip`
  Motivo: paquete regenerado después de introducir `test_assets` reales, aliases mínimos del core y workspace externo al add-on instalado.
- Archivo: `<repo>\hy3d_v2_clean_addon\hy3d_v2_clean\__init__.py`
  Motivo: creación del add-on limpio `hy3d_v2_clean` con IDs nuevos, workspace independiente, smoke local mínimo y sin dependencia del estado previo de `hy3d_v2` dentro de Blender.
- Archivo: `<repo>\hy3d_v2_clean_addon\hy3d_v2_clean\hy3d_core\...`
  Motivo: vendorizar el core local actual dentro del add-on limpio para que el paquete sea autónomo al instalarse en Blender.
- Archivo: `hy3d_v2/tests/test_clean_addon.py`
  Motivo: validar `bl_info` limpio, ausencia de IDs legacy, workspace limpio, existencia de sample assets y bloqueo de rutas vacías o `"."`.
- Archivo: `hy3d_v2/scripts/package_blender_clean_addon.py`
  Motivo: empaquetado reproducible del add-on limpio en `<repo>\dist\hy3d_v2_clean_addon.zip` sin tests, docs ni `__pycache__`.
- Archivo: `<repo>\dist\hy3d_v2_clean_addon.zip`
  Motivo: artefacto instalable limpio para Blender 5.1 con raíz `hy3d_v2_clean/`.
- Árbol instalado: `<blender_user_data>\5.1\scripts\addons\hy3d_v2_clean`
  Motivo: instalar el add-on limpio de forma aislada, sin borrar aún `hy3d_v2`.
### 2026-05-21
- Archivo: `<repo>\hy3d_v2_clean_addon\hy3d_v2_clean\__init__.py`
  Motivo: completar la integración Cloud Worker en el add-on limpio, añadir `Select Primary Image`, endurecer validaciones de rutas, reutilizar `import_result_package()` y cerrar la UI simple oficial.
- Archivo: `hy3d_v2/tests/test_clean_addon.py`
  Motivo: ampliar cobertura del add-on limpio para selección de imagen, envío a cloud, detección de `completed/failed/not_ready`, reuse del importador del core y ausencia de IDs legacy.
- Archivo: `<repo>\dist\hy3d_v2_clean_addon.zip`
  Motivo: regenerar el artefacto instalable limpio con la build `hy3d_v2_clean_20260521_1535_cloud`.
- Archivo: `<repo>\\tools\\triposr\setup_pytorch_cpu_probe.ps1`
  Motivo: crear un wrapper aislado para validar PyTorch CPU, caches y temporales fuera de `<repo>\hy3d_v2` antes de cualquier instalación local de TripoSR.
- Archivo generado: `<external_engines_root>\\triposr-local\pytorch_probe.py`
  Motivo: ejecutar un probe mínimo de importación `torch`, consulta de CUDA y operación tensorial básica dentro del venv aislado.
- Archivo generado: `<external_engines_root>\\triposr-local\pytorch_probe_report.json`
  Motivo: registrar el resultado verificable del probe PyTorch CPU (`torch_version`, `cuda_available`, `tensor_test_ok`, `tensor_test_seconds`) para decidir si conviene continuar con TripoSR local CPU.
- Archivo: `<repo>\\tools\\triposr\setup_triposr_local.ps1`
  Motivo: completar una instalación aislada y reproducible de TripoSR local sobre el venv externo, separando `torchmcubes` en modo CPU, fijando dependencias compatibles y registrando `install_report.json`.
- Archivo generado: `<external_engines_root>\\triposr-local\install_report.json`
  Motivo: dejar evidencia verificable de que el setup local sí quedó sano (`success = true`) con `torch 2.12.0+cpu`, `cuda_available = false` y duración real del setup.
- Archivo: `<repo>\\tools\\triposr\test_triposr_local.ps1`
  Motivo: validar dimensiones de imagen, exigir `real_smoke_input.png`, registrar `image_width/image_height/image_mode` en `smoke_report.json` y ejecutar el smoke real contra un asset válido antes de invertir en integración Blender.
- Archivo generado: `<external_engines_root>\\triposr-local\smoke_report.json`
  Motivo: registrar el estado final del smoke válido con `real_smoke_input.png`: `success = true`, `status = success`, `duration_seconds = 329.007`, `image_width = 512`, `image_height = 512`, `output_glb = mesh.glb` y `local_cpu_practical = true`.
- Archivo generado: `<repo>\hy3d_v2\test_assets\real_smoke_input.png`
  Motivo: repetir el smoke con una imagen real válida (`512x512`, `RGB`) derivada de `<user_downloads>\C5.jpg` después de demostrar que `sample_input.png` era `1x1` y no servía para evaluar TripoSR local CPU.
- Archivo: `<repo>\\tools\\triposr\run_triposr_local.ps1`
  Motivo: convertir una imagen local en `result_package.zip` compatible con HY3D, con validación de input, ejecución CPU, empaquetado, `run_report.json` y `error.json`.
- Archivo generado: `<external_engines_root>\\triposr-local\outputs\job_test\result_package.zip`
  Motivo: validar el empaquetado local end to end con `job_id = job_test`, `version_id = v1`, incluyendo `result_manifest.json`, `model.glb`, `engine_output/model.glb` y `logs/engine_log.txt`.
- Archivo generado: `<external_engines_root>\\triposr-local\outputs\job_test\run_report.json`
  Motivo: registrar el resultado final del wrapper local con `success = true`, `status = completed`, `duration_seconds = 73.04`, `result_package.zip` y `local_cpu_practical = true`.
### 2026-05-22
- Archivo: `<repo>\hy3d_local_connector_addon\hy3d_local_connector\__init__.py`
  Motivo: crear el add-on separado `HY3D Local Connector` con `Self Check`, `Reset Session`, selección de imagen, ejecución local de `run_triposr_local.ps1`, importación de `result_package.zip`, importación de candidato, revisión básica, aceptación a `accepted_model.glb` y exportación a `accepted_model.stl` sin tocar `hy3d_v2_clean`, el add-on legacy ni rutas cloud.
- Archivo: `<repo>\hy3d_v2\scripts\package_blender_local_connector.py`
  Motivo: empaquetado reproducible y mínimo del add-on local en `<repo>\dist\hy3d_local_connector_addon.zip`, incluyendo solo `hy3d_local_connector/__init__.py`.
- Archivo: `<repo>\hy3d_v2\tests\test_local_connector_addon.py`
  Motivo: cubrir IDs únicos del add-on, ausencia de IDs legacy, rutas del wrapper, `engine check`, validación de `result_package.zip` y bloqueo de STL cuando no existe `accepted_model.glb`.
- Archivo generado: `<repo>\dist\hy3d_local_connector_addon.zip`
  Motivo: artefacto instalable del nuevo conector local, verificado con contenido exacto `hy3d_local_connector/__init__.py`.
- Verificación ejecutada: `pytest -q hy3d_v2/tests`
  Motivo: validar el árbol actual completo después de introducir el conector local; resultado final `54 passed in 23.61s`.
- Verificación ejecutada: importación del `result_package.zip` del wrapper local mediante `_import_result_package_into_session()` del nuevo add-on fuera de Blender.
  Motivo: confirmar reutilización del contrato del core y poblar un candidato real en `<repo>\hy3d_local_connector_workspace\jobs\job_54a947ab9171\versions\v1\engine_output\model.glb`.

## HY3D Local Connector

- Estado: creado como add-on separado en `<repo>\hy3d_local_connector_addon\hy3d_local_connector`.
- Wrapper local reutilizado: `<repo>\\tools\\triposr\run_triposr_local.ps1`.
- Resultado base del wrapper: `success = true`, `status = completed`, `duration_seconds = 73.04`, `output_glb = <external_engines_root>\\triposr-local\outputs\job_test\engine_raw\0\mesh.glb`.
- `result_package.zip`: importable y ya validado previamente contra `HY3D v2 Clean`; además, el nuevo conector local ya reusa el mismo contrato del core para importarlo.
- Reglas conservadas: `model.glb` nunca se usa para STL; la ruta soportada sigue siendo `accepted_model.glb -> accepted_model.stl`.
- Errores encontrados en esta fase: ninguno nuevo en código o pruebas; el único error histórico relevante fue el BOM en `result_manifest.json`, ya corregido en el wrapper antes de esta integración.
- Pendientes: instalar `<repo>\dist\hy3d_local_connector_addon.zip` en Blender y ejecutar el smoke manual del panel/UI del add-on nuevo dentro de Blender.

## Cierre de flujo GLB/STL

- Estado: cerrado el flujo principal del conector local a nivel de contrato, archivos y pruebas.
- Flujo objetivo cubierto: `imagen -> run_triposr_local.ps1 -> result_package.zip -> model.glb candidato -> Save Basic Review -> accepted_model.glb -> accepted_model.stl -> Validate STL`.
- Botones mínimos presentes en `HY3D Local Connector`: `Self Check`, `Reset Session`, `Select Primary Image`, `Use Smoke Input`, `Check Local Engine`, `Run Local TripoSR`, `Import Local Result`, `Import Candidate GLB`, `Save Basic Review`, `Accept Selected Object`, `Export STL From Accepted`, `Validate STL`, `Open Workspace Folder`.
- `Import Local Result`: reutiliza `import_result_package()` del core y deja `candidate_manifest.json` en `versions/v1/engine_output/` y `candidate_validation_report.json` en `versions/v1/validation/`.
- `Accept Selected Object`: mantiene `source_type = selected_object` en `accepted_manifest.json` y el accepted sale a `versions/v1/accepted/accepted_model.glb`.
- `Export STL From Accepted`: bloqueado sin `accepted_model.glb`; el STL solo sale a `versions/v1/accepted/accepted_model.stl`.
- `Validate STL`: revalida `accepted_model.stl` y escribe `stl_validation_report.json` y `printability_report.json` en la carpeta `accepted/`.
- Validación mínima STL cerrada: `exists`, `file_size`, `readable`, `component_count`, `bbox`, `watertight`, `manifold`, `printability_status`, con degradación honesta a `validation_unavailable` cuando no hay stack geométrico suficiente.
- Dependencias opcionales: la validación usa `trimesh` cuando está disponible, intenta `pyvista` cuando está disponible y no bloquea todo si falta alguno.
- Smoke de contrato ejecutado fuera de Blender:
  - workspace: `<repo>\hy3d_local_connector_workspace_smoke`
  - job_id: `job_31e840aabde1`
  - candidato: `<repo>\hy3d_local_connector_workspace_smoke\jobs\job_31e840aabde1\versions\v1\engine_output\model.glb`
  - accepted: `<repo>\hy3d_local_connector_workspace_smoke\jobs\job_31e840aabde1\versions\v1\accepted\accepted_model.glb`
  - stl: `<repo>\hy3d_local_connector_workspace_smoke\jobs\job_31e840aabde1\versions\v1\accepted\accepted_model.stl`
  - `accepted_manifest.json`: generado con `source_type = selected_object`
  - `stl_validation_report.json`: generado
  - `printability_status` del smoke: `needs_cleanup`
- Pruebas realizadas:
  - `pytest -q hy3d_v2/tests/test_phase1_flow.py hy3d_v2/tests/test_local_connector_addon.py` -> `20 passed in 4.26s`
  - `pytest -q hy3d_v2/tests` -> `56 passed in 5.07s`
  - empaquetado regenerado: `<repo>\dist\hy3d_local_connector_addon.zip`
  - contenido verificado del ZIP: solo `hy3d_local_connector/__init__.py`
- Errores encontrados en esta fase: ninguno nuevo durante el cierre GLB/STL.
- Pendientes:
  - smoke manual dentro de Blender para confirmar el flujo UI completo del objeto seleccionado real
  - validación visual del candidato y del accepted dentro de la sesión Blender

## Mesh Quality Gate

- Estado: implementado sobre el candidato `model.glb` antes de cualquier aceptación.
- Reporte nuevo: `versions/v1/validation/mesh_quality_report.json`
- Campos cubiertos: `readable`, `vertices`, `faces`, `components`, `watertight`, `non_manifold_edges`, `boundary_edges`, `bbox`, `flatness_score`, `hole_warning`, `disconnected_parts_warning`, `repair_recommended`, `repair_strategy`.
- Dependencias usadas:
  - `trimesh`: lectura principal, métricas geométricas y reparación ligera.
  - `pyvista`: lectura y fallback de métricas cuando aporta datos adicionales.
  - `pymeshfix`: no estaba instalado en esta máquina durante esta fase; el gate lo declara en `repair_strategy` y no falla por su ausencia.
- Regla aplicada: si `repair_recommended = true`, el sistema genera `repaired_candidate.glb` como candidato alternativo en `versions/v1/engine_output/repaired_candidate.glb`. Nunca se promociona a `accepted_model.glb` automáticamente.
- Comparación habilitada en el add-on local:
  - `Import Candidate GLB` para `model.glb`
  - `Import Repaired Candidate GLB` para `repaired_candidate.glb`
  - Ninguno se acepta automáticamente.
- Smoke real del gate sobre `<external_engines_root>\\triposr-local\outputs\job_test\result_package.zip`:
  - workspace: `<repo>\hy3d_local_connector_mesh_gate_smoke`
  - job_id: `job_33130767d4c2`
  - `mesh_quality_report.json`: generado
  - `repair_recommended`: `true`
  - `repaired_candidate.glb`: `<repo>\hy3d_local_connector_mesh_gate_smoke\jobs\job_33130767d4c2\versions\v1\engine_output\repaired_candidate.glb`
  - `repair_strategy`: `trimesh_light_repair+pymeshfix_unavailable`
- Pruebas realizadas:
  - `pytest -q hy3d_v2/tests/test_phase1_flow.py hy3d_v2/tests/test_local_connector_addon.py` -> `23 passed in 6.44s`
  - `pytest -q hy3d_v2/tests` -> `59 passed in 9.10s`
- Bitácora:
  - `hy3d_v2/hy3d_core/validation/service.py`
    Motivo: incorporar el Mesh Quality Gate, edge stats, flatness, advertencias, reparación ligera y exportación opcional de `repaired_candidate.glb`.
  - `hy3d_v2/hy3d_core/job_service.py`
    Motivo: generar `mesh_quality_report.json`, exponer `repair_recommended` y `repaired_candidate_path` en `candidate_manifest.json`.
  - `hy3d_local_connector_addon/hy3d_local_connector/__init__.py`
    Motivo: poblar `repaired_candidate_path` y añadir `Import Repaired Candidate GLB` para comparar candidato original vs reparado sin aceptación automática.
  - `hy3d_v2/tests/test_phase1_flow.py`, `hy3d_v2/tests/test_local_connector_addon.py`
    Motivo: cubrir el gate con un mesh roto sintético, la creación de `repaired_candidate.glb` y la propagación del nuevo path al conector local.

## Engine Output vs HY3D Workspace

- Problema operativo cerrado: un job puede existir primero solo como salida del motor en `<external_engines_root>\\triposr-local\outputs\job_<id>` y todavía no existir como job importado dentro del workspace HY3D.
- Separación explícita establecida:
  - salida del motor: `<external_engines_root>\\triposr-local\outputs\job_<id>`
  - job importado a HY3D: `<repo>\hy3d_local_connector_workspace\jobs\job_<hy3d_id>\versions\v1\...`
  - modelo aceptado: `...\accepted\accepted_model.glb`
  - STL final: `...\accepted\accepted_model.stl`
- Estados agregados al conector local:
  - `no_job`
  - `engine_generated`
  - `imported_to_hy3d`
  - `candidate_imported`
  - `accepted`
  - `stl_exported`
  - `stl_validated`
- Archivo nuevo de trazabilidad: `local_engine_status.json`
  - ubicación: dentro de la carpeta del motor `<external_engines_root>\\triposr-local\outputs\job_<id>\local_engine_status.json`
  - campos principales: `engine_job_id`, `engine_output_dir`, `result_package_path`, `hy3d_imported`, `hy3d_job_id`, `accepted_model_path`, `stl_path`, `stl_validation_report_path`, `printability_report_path`, `exports_folder`, `status`
- Después de `Run Local TripoSR`:
  - se guarda `engine_job_id`
  - se guarda `engine_output_dir`
  - se guarda `result_package_path`
  - estado: `engine_generated`
  - mensaje UI: `Result package generated. Next step: Import Local Result.`
- Después de `Import Local Result` o `Import Existing Result Package`:
  - se crea el job HY3D en el workspace
  - `local_engine_status.json` cambia a `hy3d_imported = true`
  - se registra `hy3d_job_id`
  - estado: `imported_to_hy3d`
- Después de `Import Candidate GLB` o `Import Repaired Candidate GLB`:
  - estado: `candidate_imported`
- Después de `Accept Selected Object`:
  - estado: `accepted`
  - se registra `accepted_model_path`
- Después de `Export STL From Accepted`:
  - estado: `stl_exported`
  - se registra `stl_path`
  - se copian artefactos al directorio fácil `<repo>\HY3D_EXPORTS\job_<engine_job_id>\`
- Después de `Validate STL`:
  - estado: `stl_validated`
  - se registran `stl_validation_report_path` y `printability_report_path`
- Botones nuevos del add-on:
  - `Import Existing Result Package`
  - `Open Engine Output Folder`
  - `Open HY3D Job Folder`
  - `Open Accepted Folder`
  - `Open Exports Folder`
- UI nueva visible:
  - `Current Status`
  - `Engine Output Folder`
  - `Result Package Path`
  - `HY3D Job Folder`
  - `Accepted Model Path`
  - `STL Path`
  - `Exports Folder`
- Cómo localizar el STL final:
  - ruta canónica del workflow: `<repo>\hy3d_local_connector_workspace\jobs\job_<hy3d_id>\versions\v1\accepted\accepted_model.stl`
  - copia fácil para entrega/inspección: `<repo>\HY3D_EXPORTS\job_<engine_job_id>\accepted_model.stl`
- Verificación real con un job del motor existente:
  - job del motor: `job_c8823241e9a5`
  - output del motor: `<external_engines_root>\\triposr-local\outputs\job_c8823241e9a5`
  - smoke de importación a workspace temporal: `<repo>\hy3d_local_connector_status_smoke`
  - resultado: `local_engine_status.json` quedó en `status = imported_to_hy3d`, `hy3d_imported = true`, `hy3d_job_id = job_5bbbd41d7c1c`
- Nueva carpeta de exportación fácil:
  - raíz: `<repo>\HY3D_EXPORTS`
  - destino por job: `<repo>\HY3D_EXPORTS\job_<engine_job_id>\`
  - contenido copiado al exportar STL: `accepted_model.stl`, `accepted_model.glb`, `stl_validation_report.json`, `printability_report.json`
- Pruebas realizadas:
  - `pytest -q hy3d_v2/tests/test_local_connector_addon.py` -> `15 passed in 5.56s`
  - `pytest -q hy3d_v2/tests` -> `63 passed in 8.02s`
  - smoke real de trazabilidad con `job_c8823241e9a5` -> importación correcta a workspace temporal y actualización real de `local_engine_status.json`
- Errores encontrados:
  - durante la implementación, `_sync_exports_from_accepted()` dependía solo del workspace; se corrigió para derivar la carpeta `accepted` directamente desde `accepted_model_path` cuando ya existe.
- Pendientes:
  - smoke manual dentro de Blender para validar visualmente los botones nuevos de apertura de carpetas y rescate de packages existentes
  - validación manual del flujo de exportación hacia `HY3D_EXPORTS` desde una sesión Blender real
- Bitácora:
  - `hy3d_local_connector_addon/hy3d_local_connector/__init__.py`
    Motivo: separar `engine_job_id` de `hy3d_job_id`, introducir estados explícitos, `local_engine_status.json`, rescate manual de `result_package.zip`, botones de apertura y copia a `HY3D_EXPORTS`.
  - `hy3d_v2/tests/test_local_connector_addon.py`
    Motivo: cubrir `engine_generated`, `Import Existing Result Package`, actualizaciones de `local_engine_status.json`, validez de carpetas abiertas, copia a `HY3D_EXPORTS` y bloqueo de STL antes de `accepted`.

## Portabilidad y trazabilidad local

- Estado: el add-on `HY3D Local Connector` ya no depende de rutas absolutas personales para resolver proyecto, motor, wrapper o exports.
- Orden de resolución de configuración:
  1. variables de entorno: `HY3D_PROJECT_ROOT`, `HY3D_ENGINE_ROOT`, `HY3D_WRAPPER_RUN`, `HY3D_EXPORTS_ROOT`
  2. archivo local opcional `hy3d_local_config.json` en la raíz del repo
  3. rutas relativas al checkout actual
- `hy3d_local_config.json` es configuración de máquina local y queda ignorado por git.
- Defaults relativos:
  - `HY3D_PROJECT_ROOT`: `<repo>/hy3d_v2`
  - `HY3D_ENGINE_ROOT`: `<parent-del-repo>/3D_ENGINES/triposr-local`
  - `HY3D_WRAPPER_RUN`: `<repo>/tools/triposr/run_triposr_local.ps1`
  - `HY3D_EXPORTS_ROOT`: `<repo>/HY3D_EXPORTS`
- `local_engine_status.json` mantiene los estados permitidos:
  - `no_job`
  - `engine_generated`
  - `imported_to_hy3d`
  - `candidate_imported`
  - `accepted`
  - `stl_exported`
  - `stl_validated`
- `Import Local Result` ya no queda bloqueado por `job_id` vacío. Si existe `result_package.zip` y hay imagen primaria o fallback `engine_raw/0/input.png`, crea/asocia el job HY3D y luego importa el resultado.
- `Import Existing Result Package` mantiene el mismo contrato: requiere un ZIP válido y crea un job HY3D local si no hay uno asociado.
- Al exportar STL desde el accepted, el conector copia a `HY3D_EXPORTS/job_<id>/`:
  - `accepted_model.glb`
  - `accepted_model.stl`
  - `stl_validation_report.json`
  - `printability_report.json`
- Reglas conservadas:
  - `model.glb` no produce STL.
  - `repaired_candidate.glb` no produce STL.
  - solo `accepted_model.glb` puede producir `accepted_model.stl`.
  - `repaired_candidate.glb` nunca se acepta automáticamente.
- Higiene de repositorio:
  - `__pycache__`, `.pyc`, workspaces, outputs de motor, `HY3D_EXPORTS`, ZIPs de distribución y `hy3d_local_config.json` quedan ignorados.
  - Se conserva `hy3d_v2/test_assets/result_package_sample.zip` como fixture mínimo de pruebas.
- Pruebas realizadas:
  - `python -m pytest hy3d_v2/tests -q` -> `62 passed, 1 skipped`
- Bitácora:
  - `.gitignore`
    Motivo: impedir versionado de cachés, workspaces, outputs, exports, configuración local y artefactos de distribución.
  - `hy3d_local_connector_addon/hy3d_local_connector/__init__.py`
    Motivo: resolver configuración por entorno/config local/defaults relativos, registrar rutas efectivas en self-check, desbloquear importación local sin `job_id` previo y mantener copia de exports por job.
  - `hy3d_v2_clean_addon/hy3d_v2_clean/__init__.py`
    Motivo: resolver assets de muestra desde el checkout actual en vez de una ruta absoluta de máquina.
  - `hy3d_v2/tests/test_local_connector_addon.py`
    Motivo: reemplazar dependencias de `<external_engines_root>` por fixtures temporales y assets locales.

## Transportar HY3D v2 a otra computadora

Objetivo: mover el repo HY3D y el motor TripoSR sin editar codigo fuente.

### Que se clona de GitHub

Clonar el repo completo:

```powershell
git clone https://github.com/Pega-568/3DV2.git
cd 3DV2
```

El repo contiene:

- `hy3d_v2/`
- `hy3d_local_connector_addon/`
- `hy3d_v2_clean_addon/`
- `tools/triposr/run_triposr_local.ps1`
- `hy3d_local_config.example.json`
- scripts y tests.

### Que no se sube al repo

No versionar:

- `hy3d_local_config.json`
- `HY3D_EXPORTS/`
- `dist/`
- workspaces `*_workspace/`
- outputs del motor
- caches `__pycache__/`, `.pytest_cache/`
- ZIPs generados.

### Entorno Python

Crear un entorno Python para trabajar con el core:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
```

Instalar las dependencias usadas por tests y validacion segun la maquina. Como minimo, el entorno debe poder ejecutar:

```powershell
python -m pytest hy3d_v2\tests -q
```

### Preparar TripoSR externo

TripoSR no se sube al repo. Ubicarlo en una carpeta externa, por ejemplo:

```text
<external_engines_root>/triposr-local/
  .venv/
  TripoSR/
    run.py
```

El wrapper versionado esta en:

```text
<repo>/tools/triposr/run_triposr_local.ps1
```

### Crear config local

Copiar el ejemplo:

```powershell
python scripts\setup_local_config.py
```

O manualmente:

```powershell
copy hy3d_local_config.example.json hy3d_local_config.json
```

Editar `hy3d_local_config.json` segun la PC:

```json
{
  "HY3D_PROJECT_ROOT": ".\\hy3d_v2",
  "HY3D_ENGINE_ROOT": "..\\3D_ENGINES\\triposr-local",
  "HY3D_WRAPPER_RUN": ".\\tools\\triposr\\run_triposr_local.ps1",
  "HY3D_EXPORTS_ROOT": ".\\HY3D_EXPORTS"
}
```

`hy3d_local_config.json` es local y no debe subirse.

Tambien se pueden usar variables de entorno:

- `HY3D_PROJECT_ROOT`
- `HY3D_ENGINE_ROOT`
- `HY3D_WRAPPER_RUN`
- `HY3D_EXPORTS_ROOT`

Orden de resolucion:

1. variables de entorno;
2. `hy3d_local_config.json`;
3. defaults relativos al repo.

### Empaquetar add-on

Generar ZIP instalable:

```powershell
python hy3d_v2\scripts\package_blender_local_connector.py
```

Salida esperada:

```text
dist/hy3d_local_connector_addon.zip
```

El ZIP debe contener solo:

```text
hy3d_local_connector/__init__.py
```

### Instalar add-on en Blender

En Blender:

1. `Edit > Preferences > Add-ons`
2. `Install...`
3. seleccionar `dist/hy3d_local_connector_addon.zip`
4. activar `HY3D Local Connector`
5. abrir el panel `HY3D Local`
6. ejecutar `Self Check`

`Self Check` debe mostrar:

- repo root;
- project root;
- engine root;
- wrapper path;
- exports root;
- si cada ruta existe;
- recomendacion si falta algo.

### Probar sin TripoSR

Una PC sin TripoSR puede revisar paquetes ya generados:

1. seleccionar o tener una imagen primaria;
2. usar `Import Existing Result Package`;
3. elegir un `result_package.zip` compatible;
4. importar candidato;
5. aceptar manualmente el objeto seleccionado;
6. exportar STL desde accepted.

Este flujo no requiere motor instalado.

### Probar con TripoSR local

Con `HY3D_ENGINE_ROOT` y `HY3D_WRAPPER_RUN` configurados:

1. `Self Check`;
2. seleccionar imagen;
3. `Run Local TripoSR`;
4. `Import Local Result`;
5. revisar candidato original y reparados;
6. aceptar manualmente;
7. exportar STL.

### Verificacion de portabilidad

Ejecutar:

```powershell
python scripts\check_portability.py
python -m pytest hy3d_v2\tests -q
```

`check_portability.py` valida que no haya rutas personales en codigo fuente principal, que exista el wrapper versionado, que exista el config example y que `hy3d_local_config.json` este ignorado.

## Mesh Repair & Quality Benchmark

- Estado: implementado sin cambiar el contrato central GLB/STL.
- Reglas conservadas:
  - `model.glb` sigue siendo el candidato original.
  - ningún candidato reparado se acepta automáticamente.
  - ningún candidato reparado puede exportar STL directamente.
  - solo `accepted_model.glb` puede generar `accepted_model.stl`.
  - no se cambia el motor de generación.
- Reporte principal extendido: `versions/<version_id>/validation/mesh_quality_report.json`
  - `exists`
  - `file_size`
  - `readable_by_trimesh`
  - `readable_by_pyvista`
  - `vertex_count`
  - `face_count`
  - `bbox`
  - `component_count`
  - `watertight`
  - `winding_consistent`
  - `euler_number`
  - `non_empty`
  - `repair_recommended`
  - `validation_warnings`
- Capa nueva: `hy3d_core/repair/service.py`
- Reparación ligera con Trimesh:
  - genera `versions/<version_id>/engine_output/repaired_candidate_light.glb` cuando corresponde y Trimesh puede procesar la malla.
  - genera `versions/<version_id>/validation/repair_report_light.json` siempre.
  - operaciones intentadas según disponibilidad de la versión instalada: `remove_duplicate_faces`, `remove_degenerate_faces`, `remove_unreferenced_vertices`, `merge_vertices`, `fix_normals`, `fill_holes`.
- Reparación opcional con PyMeshFix:
  - si `pymeshfix` está disponible, intenta generar `repaired_candidate_meshfix.glb`.
  - si no está disponible, `repair_report_meshfix.json` registra `pymeshfix_unavailable`.
  - el flujo no falla por ausencia de PyMeshFix.
- Reparación opcional con PyMeshLab:
  - si `pymeshlab` está disponible, intenta generar `repaired_candidate_meshlab.glb`.
  - si no está disponible, `repair_report_meshlab.json` registra `pymeshlab_unavailable`.
  - el flujo no falla por ausencia de PyMeshLab.
- Comparación generada:
  - `versions/<version_id>/validation/repair_comparison_report.json`
  - compara `original`, `light`, `meshfix`, `meshlab`.
  - métricas: existencia, tamaño, componentes, watertight, caras, vértices y warnings.
- Integración en `import_result_package()`:
  - primero extrae y valida `model.glb`.
  - luego genera `mesh_quality_report.json`.
  - luego ejecuta el benchmark de reparación.
  - `candidate_manifest.json` incluye:
    - `repaired_candidate_light_path`
    - `repaired_candidate_meshfix_path`
    - `repaired_candidate_meshlab_path`
    - `repaired_candidate_paths`
    - `repair_report_paths`
  - el estado del job queda en revisión de candidato, no en accepted.
- Add-on local:
  - muestra rutas para original, light, meshfix y meshlab.
  - botones:
    - `Import Original Candidate GLB`
    - `Import Light Repaired Candidate`
    - `Import MeshFix Candidate`
    - `Import MeshLab Candidate`
    - `Open Validation Folder`
  - cada importación marca objetos con:
    - `hy3d_role = candidate`
    - `hy3d_candidate_type = original/light/meshfix/meshlab`
    - `hy3d_job_id`
- Pruebas realizadas:
  - `python -m pytest hy3d_v2/tests -q` -> `62 passed, 1 skipped`
- Bitácora:
  - `hy3d_v2/hy3d_core/validation/service.py`
    Motivo: ampliar métricas de calidad y mantener degradación por dependencias opcionales.
  - `hy3d_v2/hy3d_core/repair/service.py`
    Motivo: añadir reparación ligera, backends opcionales y comparación de variantes.
  - `hy3d_v2/hy3d_core/repair/__init__.py`
    Motivo: exponer `run_repair_benchmark`.
  - `hy3d_v2/hy3d_core/job_service.py`
    Motivo: integrar benchmark después de importar `model.glb` y registrar rutas/reportes en `candidate_manifest.json`.
  - `hy3d_local_connector_addon/hy3d_local_connector/__init__.py`
    Motivo: añadir rutas y botones para importar variantes reparadas como candidatos, no como accepted.
  - `hy3d_v2/tests/test_phase1_flow.py`
    Motivo: cubrir reportes, degradación opcional, manifest y bloqueo STL desde candidatos.
  - `hy3d_v2/tests/test_local_connector_addon.py`
    Motivo: cubrir helpers/rutas del add-on para variantes reparadas.

## Fase 3 - Benchmark de calidad real

- Estado: implementado como herramienta repetible sin depender de TripoSR real.
- Script principal: `hy3d_v2/scripts/run_quality_benchmark.py`
- Entradas recomendadas: `hy3d_v2/benchmark_inputs/README_BENCHMARK_INPUTS.md`
- Plantilla manual versionada: `hy3d_v2/benchmark_reports/manual_review_template.csv`
- Outputs generados localmente e ignorados por Git:
  - `hy3d_v2/benchmark_reports/benchmark_summary.json`
  - `hy3d_v2/benchmark_reports/benchmark_summary.csv`
  - `hy3d_v2/benchmark_reports/_benchmark_workspace/`
- Modo fixture sin motor:
  - `python hy3d_v2/scripts/run_quality_benchmark.py --mode fixture --clean-workspace --workspace-root hy3d_v2/benchmark_reports/_benchmark_workspace`
- Modo paquetes existentes:
  - `python hy3d_v2/scripts/run_quality_benchmark.py --mode packages --packages-dir <folder_con_result_packages> --clean-workspace --workspace-root hy3d_v2/benchmark_reports/_benchmark_workspace`
- Modo wrapper local:
  - existe como modo explícito `wrapper`, pero queda desactivado por defecto y exige `--enable-wrapper` más `HY3D_WRAPPER_RUN`.
- Campos del summary:
  - `input_name`, `job_id`, `version_id`, rutas de candidato original/reparados, rutas de reportes, existencia de cada variante, métricas originales, watertight por variante, `repair_recommended`, warnings y campos manuales editables.
- Reglas conservadas:
  - `model.glb` sigue siendo candidato original.
  - `repaired_candidate_light.glb`, `repaired_candidate_meshfix.glb` y `repaired_candidate_meshlab.glb` siguen siendo candidatos reparados.
  - ningún candidato se acepta automáticamente.
  - ningún candidato original o reparado exporta STL.
  - solo `accepted_model.glb` puede producir `accepted_model.stl`.
- Pruebas agregadas:
  - generación de summary JSON.
  - generación de CSV.
  - modo fixture sin motor.
  - modo packages con ZIP existente.
  - paths relativos al workspace y sin rutas absolutas locales.

## Fase 4 - Input quality y perfiles de reparación

- Estado: implementado sin cambiar de motor y sin aceptar candidatos automáticamente.
- Módulo nuevo: `hy3d_v2/hy3d_core/input_quality/service.py`
- Función principal: `analyze_input_image(image_path)`
- Reporte nuevo por job: `versions/<version_id>/validation/input_quality_report.json`
- Campos del reporte:
  - `image_path`
  - `exists`
  - `file_size`
  - `width`
  - `height`
  - `mode`
  - `aspect_ratio`
  - `has_alpha`
  - `is_too_small`
  - `is_square_or_near_square`
  - `contrast_score`
  - `estimated_background_complexity`
  - `input_quality_status`
  - `warnings`
- Integración en `create_job()`:
  - copia la imagen primaria al job.
  - analiza la copia local.
  - escribe `input_quality_report.json`.
  - registra `input_quality_status`, `input_quality_warnings` e `input_quality_report_path` en `job_manifest.json`.
  - propaga warnings al `multi_view_validation_report.json`.
- Regla operativa:
  - archivo inexistente o formato no soportado siguen bloqueados antes de crear job.
  - imágenes pequeñas, bajo contraste, fondo complejo o formato no cuadrado quedan como advertencias para no romper el flujo local ya validado.
- Perfiles de reparación agregados:
  - `safe_light`: default.
  - `visual_preserve`: evita cerrar agujeros para preservar cavidades visibles.
  - `printability`: prioriza watertight/manifold cuando la herramienta disponible lo permite.
  - `aggressive_close_holes`: registra advertencia fuerte porque puede cerrar cavidades reales.
- Reportes de reparación extendidos:
  - `repair_profile`
  - `operations_applied`
  - `warnings`
  - `before_metrics`
  - `after_metrics`
  - `technical_recommendation`
  - `no_auto_acceptance: true`
- `repair_comparison_report.json` ahora registra el perfil usado, operaciones, warnings agregados y recomendación técnica.
- Integración en `import_result_package()`:
  - parámetro opcional `repair_profile`, default `safe_light`.
  - `candidate_manifest.json` conserva rutas de candidatos reparados e incluye `repair_profile`.
- Add-on `HY3D Local Connector`:
  - muestra estado y warnings de input quality.
  - guarda esos datos en `local_engine_status.json`.
  - expone selector `Repair Profile`.
  - pasa el perfil seleccionado al importar el resultado.
- Reglas conservadas:
  - `model.glb` sigue siendo candidato original.
  - `repaired_candidate_light.glb`, `repaired_candidate_meshfix.glb` y `repaired_candidate_meshlab.glb` siguen siendo candidatos reparados.
  - ningún candidato reparado se acepta automáticamente.
  - ningún candidato reparado exporta STL.
  - solo `accepted_model.glb` puede producir `accepted_model.stl`.
- Pruebas agregadas:
  - imagen válida.
  - imagen pequeña.
  - generación de `input_quality_report.json` desde `create_job()`.
  - reportes perfilados de reparación.
  - registro de perfil en `candidate_manifest.json` y `repair_comparison_report.json`.
  - bloqueo de STL sin accepted.
  - propagación del perfil desde el conector local.

## Fase 2 - Smoke Blender y limpieza de escena

- Estado: parcialmente implementado fuera de Blender; smoke manual pendiente.
- Bloqueo del smoke manual: Blender no estaba disponible en `PATH` durante esta fase, por lo que no se pudo ejecutar el flujo UI real desde esta máquina.
- Botón agregado al add-on local:
  - `Clear HY3D Objects From Scene`
- Regla implementada:
  - elimina únicamente objetos que tengan `hy3d_job_id` y `hy3d_role` en `candidate` o `accepted`.
  - no elimina objetos externos del usuario.
- Metadata respetada:
  - candidatos importados: `hy3d_role = candidate`, `hy3d_candidate_type = original/light/meshfix/meshlab`, `hy3d_source_path`, `hy3d_job_id`.
  - accepted: `hy3d_role = accepted`, `hy3d_source_path`, `hy3d_job_id`.
- Pruebas realizadas:
  - `python -m pytest hy3d_v2/tests -q` -> pendiente de la verificación final de esta fase.
- Pendiente manual:
  - abrir Blender con el add-on instalado.
  - ejecutar el smoke completo desde `Self Check` hasta `Open Exports Folder`.
  - confirmar visualmente que no hay contaminación por objetos de jobs anteriores.

