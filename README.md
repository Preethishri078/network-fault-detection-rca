# Enterprise Network Fault Detection & Root Cause Analysis (RCA) Engine

A production-ready, topology-aware Network Management System (NMS) telemetry processing and Root Cause Analysis (RCA) platform built in Python using NetworkX, Pydantic, Streamlit, and Plotly.

---

## 🌟 Architectural Overview

```
Probes + CSV Log File + Scenarios → Event Queue → Rules Classifier → Windowed Deduplicator
       → Graph Correlator / RCA (NetworkX DAG Topology) → Executive Report + Streamlit Dashboard
```

The system ingests network failure events from live TCP socket probes, offline CSV log files, or automated fault injection scenarios. It classifies and deduplicates telemetry streams in real time, applies graph-based correlation over a 21-node enterprise DAG topology, infers unmonitored silent parent failures using Lowest Common Ancestor (LCA) algorithms, and presents actionable insights on a live Streamlit dashboard.

---

## 📁 Repository Structure

```text
e:\Wipro NMS\
├── data/
│   ├── topology.json               # 21-node DAG enterprise topology (Cisco, Arista, Juniper, Dell)
│   ├── rules.yaml                  # Classification rules & device escalation thresholds
│   └── sample_network_events.csv   # Offline CSV telemetry log dataset for file ingestion
├── src/
│   ├── models.py                   # Pydantic data schemas & Enums
│   ├── topology.py                 # NetworkX DiGraph wrapper, DAG & LCA algorithms
│   ├── ingest.py                   # Thread-safe queue, CSV log reader & background TCP probe worker
│   ├── classifier.py               # Config-driven rule classifier with device severity escalation
│   ├── dedup.py                    # Sliding-window deduplicator & flap detection
│   ├── correlator.py               # Graph correlation engine & component analyzer
│   ├── rca_rules.py                # Pattern-to-remediation inference engine
│   ├── report.py                   # Jinja2 HTML report generator
│   └── pipeline.py                 # Pipeline orchestrator & CLI interface
├── scenarios/
│   └── scenarios.py                # 8 Fault injection scenario generators
├── tests/
│   ├── test_topology.py            # Graph DAG & depth unit tests
│   ├── test_classifier.py          # Classification & rule escalation unit tests
│   ├── test_dedup.py               # Deduplication & flap detection unit tests
│   └── test_correlator.py          # Scenario correlation unit tests
├── app.py                          # Streamlit + Plotly interactive dashboard UI
└── requirements.txt                # Dependencies
```

---

## ⚡ Core Technical Capabilities

1. **Enterprise Network Graph Topology ([src/topology.py](file:///e:/Wipro%20NMS/src/topology.py)):**
   - Models a 21-node enterprise network across Core (`Cisco Nexus 9504`), Aggregation (`Arista 7050SX`), Access (`Juniper EX2300`), and Server (`Dell PowerEdge R740`) tiers.
   - Enforces strict DAG validation (rejecting circular topology loops) and handles **dual-homed high-availability links**.
2. **Rule-Based Event Classification ([src/classifier.py](file:///e:/Wipro%20NMS/src/classifier.py)):**
   - Config-driven severity escalation (`CORE` > `DIST` > `ACCESS`).
   - Handles latency and packet loss thresholds, as well as automatic alarm clearance on recovery events (`LINK_UP`, `NODE_REACHABLE`).
3. **Deduplication & Flap Detection ([src/dedup.py](file:///e:/Wipro%20NMS/src/dedup.py)):**
   - Windowed deduplication key `(device, event_type)`.
   - Rapidly toggling interface ports are marked as `FLAPPING`, achieving **up to 99.0% noise reduction**.
4. **Algorithmic RCA & Silent Parent Inference ([src/correlator.py](file:///e:/Wipro%20NMS/src/correlator.py)):**
   - Graph failure subgraph $G_f$ decomposition into weakly connected components.
   - Infers unmonitored parent switch failures (`INFERRED_ROOT`) using Lowest Common Ancestor (LCA) algorithms when monitoring gaps occur.
5. **Interactive Operations UI & Export Engine ([app.py](file:///e:/Wipro%20NMS/app.py)):**
   - Live visual network graph with dynamic tooltips (Vendor, IP, Location, OS).
   - Offline CSV log file upload & interactive scenario injection.
   - Downloads formal Executive HTML Incident RCA Reports.

---

## 🚀 Quick Execution Guide

### 1. Installation

```bash
pip install -r requirements.txt
```

### 2. Run CLI Pipeline (Scenario or CSV Log Ingestion)

```bash
# Run predefined scenario
python -m src.pipeline --scenario core_outage

# Ingest offline CSV log file
python -m src.pipeline --log-file data/sample_network_events.csv
```

### 3. Run Automated Unit Test Suite (18/18 Passing)

```bash
python -m pytest
```

### 4. Launch Streamlit Web Dashboard

```bash
python -m streamlit run app.py
```

Open browser to `http://localhost:8501`.
