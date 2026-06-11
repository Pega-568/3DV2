# TripoSR local portable setup

HY3D does not vendor the TripoSR engine. Keep the engine outside the repo, then point HY3D to it with one of these options:

1. Environment variable `HY3D_ENGINE_ROOT`.
2. Local ignored config file `hy3d_local_config.json`.
3. A relative folder such as `../3D_ENGINES/triposr-local`, `external_engines/triposr-local`, or `engines/triposr-local`.

Expected engine layout:

```text
triposr-local/
  .venv/
    Scripts/python.exe
  TripoSR/
    run.py
```

The portable wrapper is:

```text
tools/triposr/run_triposr_local.ps1
```

It accepts:

- `-input_image`
- `-output_dir`
- `-job_id`
- `-version_id`
- optional `-engine_root`

It writes `run_report.json`, `result_manifest.json`, `result_package.zip`, and copies the engine mesh to `engine_raw/0/mesh.glb`.
