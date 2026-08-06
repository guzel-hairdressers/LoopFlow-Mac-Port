# LoopFlow Long-Term Issue & Performance Tracker

This document tracks active, resolved, and long-term architectural issues and performance targets for **LoopFlow Mac Port**.

---

## 1. Resolved Issues & Milestones

| ID | Title | Component | Resolved In | Status |
| :--- | :--- | :--- | :--- | :---: |
| **ISSUE-01** | Layer visibility updates forcing 4-minute full model re-read | `read3dm.py` | v0.0.52 | RESOLVED ✅ |
| **ISSUE-02** | Stale script directory execution in Rhino (`Py` vs `Python`) | `LiveLink_R2B_Fast.py` | v0.0.52 | RESOLVED ✅ |
| **ISSUE-03** | Block Instance $O(N \times M)$ nested loop bottleneck (99s delay) | `converters/instances.py` | v0.0.52 | RESOLVED ✅ |
| **ISSUE-04** | Fast-path collection lookup failing on duplicate layer names | `converters/layers.py` | v0.0.52 | RESOLVED ✅ |
| **ISSUE-05** | UI button & icon terminology alignment (`Model Sync`, `Fast Sync`) | `__init__.py` / `.rhc` | v0.0.52 | RESOLVED ✅ |
| **ISSUE-06** | Re-add standalone **Import Model** button to sidebar panel | `__init__.py` | v0.0.52 | RESOLVED ✅ |

---

## 2. Performance Metric Tracking (Reference Model: Game Center Roof.3dm - 199.85 MB)

| Target ID | Operation | Target Limit | Measured Time | Status |
| :--- | :--- | :---: | :---: | :---: |
| **PERF-01** | Geometry Deletion | $< 20.0\text{s}$ | **2.57s** | PASS ✅ |
| **PERF-02** | Update Model (No Changes) | $< 20.0\text{s}$ | **0.98s** | PASS ✅ |
| **PERF-03** | Update Model (Layer Visibility Changed) | $< 30.0\text{s}$ | **0.62s** | PASS ✅ |
| **PERF-04** | Update Model (Geometry Changed) | $< 60.0\text{s}$ | **2.90s** | PASS ✅ |

---

## 3. Performance Log File Location

Suboperation timings and RAM footprint logs are appended in single-line JSONLines format to:
`~/Library/Application Support/McNeel/Rhinoceros/8.0/scripts/LoopFlow_R2B/Data/LoopFlow_Performance.log`
