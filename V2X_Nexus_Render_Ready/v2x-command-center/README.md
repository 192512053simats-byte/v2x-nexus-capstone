# V2X Nexus — AI-enabled Cooperative Perception Research Dashboard

A **runnable, local website** for the capstone **AI-Enabled Communication-Aware Cooperative Perception for 6G-V2X Networks**.

This is an **illustrative software simulation**, not an operational 6G radio stack or a verified autonomous driving system. It combines a vehicle-motion generator, simplified sensing, capacity-limited V2X-style messages, priority scheduling, deduplicated cooperative awareness, and paired experiments.

## Start on Windows — simplest method

1. Install **Python 3.10 or newer** from https://www.python.org/downloads/ (enable **Add Python to PATH** during installation).
2. Extract the ZIP file, then **double-click `start_windows.bat`**.
3. The dashboard opens at **http://127.0.0.1:5000**. If it did not open automatically, paste that address into Chrome.
4. Click **Run Comparison**. Choose a road scenario, number of vehicles, network congestion, and channel capacity. A matched baseline (FIFO) and proposed AI-priority run are computed using the same traffic and message demand.
5. Switch between **AI Priority / FIFO Baseline** above the playback controls to compare the traffic and message effects. Use **Download CSV** or **Export Data** to save results.

**No installation packages are required for the basic website.** `server.py` uses the Python standard library. If the optional machine-learning package is absent, the scheduler uses a transparent urgency heuristic rather than a trained classifier.

### Run from the VS Code terminal

```powershell
cd v2x-command-center
python server.py
```

Then open `http://127.0.0.1:5000`. Press `Ctrl+C` to stop.

## Enable an actual scikit-learn model (optional, recommended for AI capstone)

```powershell
python -m pip install "scikit-learn>=1.4,<2"
python server.py
```

Open **http://127.0.0.1:5000/api/health** to verify the `ai.kind` field:

- `supervised-synthetic` — Random Forest fitted to **generated policy labels** using packet urgency, severity, age, proximity, deadline and congestion.
- `heuristic` — deterministic hand-designed priority score when scikit-learn isn't installed.

**Important:** Random Forest is trained with *synthetic teacher labels*, not ground-truth real traffic safety outcomes. Its training is intended to demonstrate an ML pipeline, not demonstrate real-world generalisation. Describing it simply as “AI” without stating the synthetic training basis would be misleading.

## How it works

1. **Traffic**: Generate deterministic connected-vehicle positions for an intersection, urban roads, or highway; optionally read a SUMO trace.
2. **Local perception**: Generate a hazard and identify which nearby target vehicles can observe it directly versus which have a simulated blind spot.
3. **Message creation**: Construct routine telemetry and repeated hazard warnings. Store a deadline and target vehicle for each packet.
4. **Network**: Allocate a fixed number of packet transmissions per 100 ms tick, adjusted for congestion. Some packets are lost or expire; channel outcomes are fixed by seed and message ID, allowing paired comparison.
5. **Priority**: FIFO uses arrival order. The proposed method ranks packets with a small Random Forest or interpretable fallback, prioritising hazard severity, proximity, deadline and age.
6. **Fusion**: Delivered, on-time hazard observations expand each target vehicle's set of known hazards; duplicate messages do not grant multiple awareness credits.
7. **Evaluation**: Compute end-to-end latency, packet delivery ratio, safety-packet delivery, local+shared hazard awareness, blind-spot reduction, timely delivery, traffic bytes and queue depth.

### Comparison outputs

- **Average message latency**: average time (ms) of messages that reached the simulated receiving side.
- **Safety message latency**: mean latency (ms) of successfully delivered hazard packets.
- **Packet delivery ratio**: successfully delivered packets / all generated packets (some packets may still be queued at experiment end).
- **Safety packet delivery**: successfully delivered safety packets / generated safety packets.
- **Hazard awareness**: (`locally seen vehicle-hazard pairs + newly informed blind vehicle-hazard pairs`) / all relevant vehicle-hazard pairs; summary evaluated across the generated events.
- **Blind-spot reduction**: blind target pairs informed by timely V2X messages / all initially blind target pairs.
- **Channel data**: bytes *transmitted*, including packets that the channel lost. This is not total traffic generated.

The plot is a per-tick average, and the visual traffic is a **schematic** representation. Outputs depend on the chosen parameters; no predetermined improvement values are hardcoded into the charts.

## Optional: use real SUMO vehicle positions

This website runs immediately with built-in synthetic motion. SUMO integration is **trace-based**, not live synchronisation. `tools/import_sumo_fcd.py` can ingest SUMO FCD XML without importing the SUMO Python libraries.

1. Install SUMO separately from https://sumo.dlr.de/docs/Downloads.php and prepare a working `.sumocfg` traffic scenario.
2. Export FCD with **100 ms** sampling:

   ```powershell
   sumo -c your_scenario.sumocfg --step-length 0.1 --fcd-output trace.xml
   ```

3. From the project directory, convert the resulting XML:

   ```powershell
   python tools/import_sumo_fcd.py trace.xml --out data/sumo_trace.json --limit 48
   ```

4. In the dashboard, set **Traffic Source → Imported SUMO Trace** and run the experiment.

The importer maps SUMO geometry into canvas coordinates and converts headings for visualisation. **Traffic positions originate from SUMO**, while hazards, sensor visibility, messages and channel conditions remain simplified synthetic models. On imported traces, the map background remains a schematic road, not the original SUMO map.

The importer expects ≥8 sampled timesteps with ≥3 vehicles each. If SUMO outputs at a different step period, adjust the sampling so that the website's 100 ms tick matches the exported positions.

## What is NOT connected yet

- **ns-3 / 5G-LENA**: not integrated; the networking model uses simplified Python queues, probabilistic packet loss and deterministic jitter. Do not label those results as 5G-LENA PHY/MAC simulation measurements.
- **6G air interface**: not implemented or validated; the project is 6G-*inspired* and simulation-focused.
- **Camera/LiDAR perception**: no images or physical sensing; visibility is a lightweight randomised abstraction.
- **Live SUMO/TraCI**: not running inside this website; SUMO is supported via recorded FCD traces.

The next research-grade step would be a SUMO+TraCI mobility bridge and packet-level ns-3 channel/PHY/MAC integration, followed by experiments across multiple runs with statistical confidence intervals and evaluation of independent/non-synthetic AI labels.

## Files

```text
v2x-command-center/
├── server.py                 # Zero-dependency local HTTP + API server
├── app.py                    # Optional Flask equivalent if Flask is installed
├── engine.py                 # Traffic, hazards, messages, experiment, metrics
├── ai_model.py               # Synthetic-label RF + interpretable fallback
├── templates/index.html     # Dashboard markup
├── static/css/styles.css    # Responsive dark command-center styling
├── static/js/app.js         # Controls, canvas playback, charts, exports
├── tools/import_sumo_fcd.py # SUMO FCD XML → JSON trace converter
├── tests/test_engine.py     # Reproducibility + API checks
├── requirements.txt         # Optional Flask + scikit-learn requirements
└── start_windows.bat        # Double-click launcher on Windows
```

## Reproduce an experiment

- Keep the same `seed` and configuration to reproduce identical outputs.
- Set a small `capacity` and high `load` to investigate congestion.
- Compare results for different capacities, vehicle counts and several independent seeds.
- Record scenario, count, load, capacity, seed, algorithm and metric definitions when reporting results.
- Plot and discuss **both benefits and costs**. Prioritisation may improve timeliness but also increase traffic sent or affect the delivery of low-priority messages.

## Run tests

```powershell
python -m unittest discover -s tests -v
```

## Security / deployment

Local-only server binds to `127.0.0.1`. Do not expose the Python development server on the public internet without a proper production application deployment process.

## Host this website online

For a GitHub + Render free-tier deployment, follow [DEPLOY_RENDER.md](DEPLOY_RENDER.md). The included `render.yaml` configures the Gunicorn server and health endpoint.
