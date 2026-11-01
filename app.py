import time
import json
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from pathlib import Path

from src.pipeline import Pipeline
from src.report import ReportGenerator
from src.models import AlarmRole, AlarmStatus, Severity, DeviceType

# Streamlit Page Configuration
st.set_page_config(
    page_title="NMS Network Fault Detection & RCA Platform",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize Session State
if "pipeline" not in st.session_state:
    st.session_state.pipeline = Pipeline()
if "last_action" not in st.session_state:
    st.session_state.last_action = None

pipeline: Pipeline = st.session_state.pipeline
topology = pipeline.topology

# --- Sidebar Control Panel ---
st.sidebar.title("Control Panel")
st.sidebar.markdown("---")

st.sidebar.subheader("Telemetry Data Source")

data_source = st.sidebar.radio(
    "Select Input Method",
    options=["Predefined Fault Scenarios", "Upload Offline CSV Log File"]
)

if data_source == "Predefined Fault Scenarios":
    scenario = st.sidebar.selectbox(
        "Select Scenario",
        options=[
            "core_outage",
            "leaf_failure",
            "duplicate_storm",
            "redundant_path",
            "double_fault",
            "silent_parent",
            "flapping_link",
            "recovery"
        ],
        format_func=lambda x: {
            "core_outage": "Core Router Outage (Cisco Nexus 9K)",
            "leaf_failure": "Access Switch Failure (Juniper EX2300)",
            "duplicate_storm": "Duplicate Alarm Storm (100x)",
            "redundant_path": "Redundant Path Failover Check",
            "double_fault": "Simultaneous Double Fault",
            "silent_parent": "Silent Parent (Unmonitored Switch)",
            "flapping_link": "Flapping Link Port Instability",
            "recovery": "Clear Alarms & Restore Network"
        }[x]
    )

    if st.sidebar.button("Run Scenario", use_container_width=True, type="primary"):
        with st.spinner("Processing event telemetry and building graph components..."):
            time.sleep(0.3)  # Realistic network processing delay
            incidents = pipeline.run_scenario(scenario)
            st.session_state.last_action = f"Scenario: '{scenario}'"
        st.success(f"Executed scenario: {scenario}")

else:
    uploaded_file = st.sidebar.file_uploader("Upload CSV Network Log", type=["csv"])
    if uploaded_file is not None:
        if st.sidebar.button("Process Log File", use_container_width=True, type="primary"):
            temp_path = Path("scratch/uploaded_log.csv")
            temp_path.parent.mkdir(parents=True, exist_ok=True)
            with open(temp_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            
            with st.spinner("Ingesting CSV logs and performing graph RCA..."):
                time.sleep(0.4)
                incidents = pipeline.run_csv_file(temp_path)
                st.session_state.last_action = f"CSV File: {uploaded_file.name}"
            st.success(f"Processed file: {uploaded_file.name}")

st.sidebar.markdown("---")

st.sidebar.subheader("Correlation Window Parameters")
dedup_window = st.sidebar.slider("Deduplication Window (sec)", 5, 120, 30)
pipeline.deduplicator.sliding_window = pd.Timedelta(seconds=dedup_window)

if st.sidebar.button("Reset Network State", use_container_width=True):
    pipeline.deduplicator.active_alarms.clear()
    pipeline.deduplicator.raw_events_count = 0
    pipeline.deduplicator.unique_alarms_count = 0
    pipeline.incidents.clear()
    st.rerun()

# --- Main Dashboard Header ---
st.title("Network Fault Detection & Root Cause Analysis Engine")
st.caption("Enterprise NMS Telemetry Analytics & Topology-Aware Alert Suppression")

metrics = pipeline.get_metrics()
incidents = pipeline.incidents

# Metric Cards Row
c1, c2, c3, c4 = st.columns(4)
c1.metric("Raw Events Ingested", metrics["raw_events"])
c2.metric("Unique Active Alarms", metrics["unique_alarms"])
c3.metric("Actionable Incidents", metrics["active_incidents"])
c4.metric("Noise Reduction %", f"{metrics['noise_reduction_pct']:.1f}%")

st.markdown("---")

# Visual Layout: Left = Topology Graph, Right = RCA Summary & Alarms
col_left, col_right = st.columns([6, 5])

with col_left:
    st.subheader("Network Topology Graph")

    active_alarms = pipeline.deduplicator.get_active_alarms()
    active_map = {a.source_device: a for a in active_alarms if a.status == AlarmStatus.ACTIVE}

    node_x = []
    node_y = []
    node_color = []
    node_text = []
    node_size = []
    node_ids = list(topology.devices.keys())

    layer_groups = {
        DeviceType.CORE: [n for n, d in topology.devices.items() if d.type == DeviceType.CORE],
        DeviceType.DIST: [n for n, d in topology.devices.items() if d.type == DeviceType.DIST],
        DeviceType.ACCESS: [n for n, d in topology.devices.items() if d.type == DeviceType.ACCESS],
        DeviceType.SERVER: [n for n, d in topology.devices.items() if d.type == DeviceType.SERVER],
    }

    pos = {}
    y_coords = {DeviceType.CORE: 3.0, DeviceType.DIST: 2.0, DeviceType.ACCESS: 1.0, DeviceType.SERVER: 0.0}

    for dev_type, nodes in layer_groups.items():
        n_count = len(nodes)
        y = y_coords[dev_type]
        for idx, nid in enumerate(nodes):
            x = (idx + 1) * (10.0 / (n_count + 1))
            pos[nid] = (x, y)

    edge_x = []
    edge_y = []
    for parent, child in topology.graph.edges():
        if parent in pos and child in pos:
            x0, y0 = pos[parent]
            x1, y1 = pos[child]
            edge_x.extend([x0, x1, None])
            edge_y.extend([y0, y1, None])

    edge_trace = go.Scatter(
        x=edge_x, y=edge_y,
        line=dict(width=1.5, color='#7f8c8d'),
        hoverinfo='none',
        mode='lines'
    )

    for nid in node_ids:
        x, y = pos[nid]
        node_x.append(x)
        node_y.append(y)

        dev = topology.devices[nid]

        color = "#2ecc71"  # Healthy Green
        size = 18

        if nid in active_map:
            alarm = active_map[nid]
            if alarm.role == AlarmRole.PRIMARY_FAULT:
                color = "#e74c3c"  # Red
                size = 26
            elif alarm.role == AlarmRole.SECONDARY_CORRELATED:
                color = "#e67e22"  # Orange
                size = 20
            elif alarm.role == AlarmRole.FLAPPING:
                color = "#f1c40f"  # Yellow
                size = 22
            else:
                color = "#e74c3c"
                size = 22
        else:
            for inc in incidents:
                if inc.root_cause_device == nid and inc.inferred_root:
                    color = "#9b59b6"  # Purple for inferred root
                    size = 28
                    break

        node_color.append(color)
        node_size.append(size)

        status_str = active_map[nid].role.value if nid in active_map else "HEALTHY"
        hover_info = (
            f"<b>Device ID:</b> {nid}<br>"
            f"<b>Type:</b> {dev.type.value}<br>"
            f"<b>IP:</b> {dev.ip}<br>"
            f"<b>Location:</b> {dev.location}<br>"
            f"<b>Description:</b> {dev.role_description or 'N/A'}<br>"
            f"<b>Status:</b> {status_str}"
        )
        node_text.append(hover_info)

    node_trace = go.Scatter(
        x=node_x, y=node_y,
        mode='markers+text',
        hoverinfo='text',
        text=[nid.split('-')[-1] for nid in node_ids],
        textposition="top center",
        hovertext=node_text,
        marker=dict(
            color=node_color,
            size=node_size,
            line=dict(width=2, color='#2c3e50')
        )
    )

    fig = go.Figure(
        data=[edge_trace, node_trace],
        layout=go.Layout(
            showlegend=False,
            hovermode='closest',
            margin=dict(b=20, l=10, r=10, t=20),
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            height=460
        )
    )

    st.plotly_chart(fig, use_container_width=True)

    st.markdown("""
    **Node Legend:** 
    <span style='color:#2ecc71'>🟢 Healthy</span> | 
    <span style='color:#e74c3c'>🔴 Primary Fault</span> | 
    <span style='color:#e67e22'>🟠 Secondary Correlated (Suppressed)</span> | 
    <span style='color:#9b59b6'>🟣 Inferred Root (Monitoring Gap)</span> | 
    <span style='color:#f1c40f'>🟡 Flapping</span>
    """, unsafe_allow_html=True)


with col_right:
    st.subheader("Root Cause Analysis Insights")

    if not incidents:
        st.info("Network operational. No active root cause incidents detected.")
    else:
        for idx, inc in enumerate(incidents, 1):
            st.error(f"### Incident #{idx}: {inc.root_cause_device}")

            st.write(f"**Probable Cause:** {inc.probable_cause}")
            st.write(f"**Diagnostic Confidence:** `{inc.confidence}%`")
            st.write(f"**Severity:** `{inc.severity.value}`")
            st.write(f"**Root Cause Type:** `{'INFERRED (Silent Parent)' if inc.inferred_root else 'DIRECT ALARM'}`")

            st.markdown("**Actionable Remediation Steps:**")
            for rec in inc.recommendations:
                st.markdown(f"- {rec}")

            st.markdown("---")

    # Export Report Button
    if incidents:
        report_gen = ReportGenerator(topology)
        report_html = report_gen.generate_html_report(
            incident=incidents[0],
            raw_events_count=metrics["raw_events"],
            unique_alarms_count=metrics["unique_alarms"],
            noise_reduction_pct=metrics["noise_reduction_pct"]
        )

        st.download_button(
            label="Download Executive RCA Incident Report (HTML)",
            data=report_html,
            file_name=f"RCA_Report_{incidents[0].incident_id[:8]}.html",
            mime="text/html",
            use_container_width=True
        )

# Bottom Section: Active Alarms Table
st.markdown("---")
st.subheader("Active Deduplicated Alarm Table")

active_alarms_list = pipeline.deduplicator.get_active_alarms()
if not active_alarms_list:
    st.write("No active alarms.")
else:
    df_alarms = pd.DataFrame([
        {
            "Alarm ID": a.alarm_id[:8],
            "Device Hostname": a.source_device,
            "Event Type": a.event_type.value,
            "Severity": a.severity.value,
            "Role": a.role.value,
            "Occurrences": a.occurrence_count,
            "Flapping": "Yes" if a.is_flapping else "No",
            "First Seen": a.first_seen.strftime("%H:%M:%S"),
            "Last Seen": a.last_seen.strftime("%H:%M:%S")
        }
        for a in active_alarms_list
    ])
    st.dataframe(df_alarms, use_container_width=True)
