from datetime import datetime
from typing import List, Dict, Any, Optional
from jinja2 import Template
from src.models import Incident, Alarm
from src.topology import NetworkTopology


HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Incident RCA Report - {{ incident.incident_id }}</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 20px; background-color: #f4f6f9; color: #333; }
        .container { max-width: 1100px; margin: 0 auto; background: #fff; padding: 30px; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
        .header { border-bottom: 2px solid #e1e4e8; padding-bottom: 15px; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center; }
        .header h1 { margin: 0; color: #1a2530; font-size: 24px; }
        .badge { padding: 6px 14px; border-radius: 20px; font-weight: bold; font-size: 14px; color: #fff; text-transform: uppercase; }
        .badge-CRITICAL { background-color: #d9534f; }
        .badge-MAJOR { background-color: #f0ad4e; }
        .badge-MINOR { background-color: #5bc0de; }
        .badge-INFO { background-color: #5cb85c; }
        
        .section { margin-bottom: 30px; }
        .section-title { font-size: 18px; font-weight: 600; color: #2c3e50; border-left: 4px solid #3498db; padding-left: 10px; margin-bottom: 15px; }
        
        .summary-card { background-color: #ebf5fb; border: 1px solid #aed6f1; border-radius: 6px; padding: 18px; margin-bottom: 20px; }
        .summary-card p { margin: 0; line-height: 1.6; font-size: 15px; }
        
        .metrics-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin-bottom: 25px; }
        .metric-box { background: #f8f9fa; border: 1px solid #e9ecef; border-radius: 6px; padding: 15px; text-align: center; }
        .metric-value { font-size: 24px; font-weight: bold; color: #2c3e50; }
        .metric-label { font-size: 12px; color: #7f8c8d; text-transform: uppercase; margin-top: 5px; }

        table { width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 14px; }
        th, td { padding: 12px 15px; text-align: left; border-bottom: 1px solid #e1e4e8; }
        th { background-color: #f8f9fa; font-weight: 600; color: #495057; }
        tr:hover { background-color: #f1f3f5; }

        .role-tag { padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: bold; }
        .role-PRIMARY_FAULT { background-color: #fadbd8; color: #78281f; }
        .role-SECONDARY_CORRELATED { background-color: #fdebd0; color: #7e5109; }
        .role-STANDALONE { background-color: #e8f8f5; color: #117a65; }
        .role-INFERRED_ROOT { background-color: #f5eeed; color: #6c3483; }

        .remediation-list { padding-left: 20px; line-height: 1.8; }
        .remediation-list li { margin-bottom: 8px; }
        
        .footer { text-align: center; margin-top: 30px; font-size: 12px; color: #95a5a6; border-top: 1px solid #eee; padding-top: 15px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div>
                <h1>Network Incident Root Cause Analysis</h1>
                <div style="font-size: 13px; color: #7f8c8d; margin-top: 5px;">Incident ID: {{ incident.incident_id }} | Generated: {{ generated_at }}</div>
            </div>
            <span class="badge badge-{{ incident.severity.value }}">{{ incident.severity.value }}</span>
        </div>

        <div class="metrics-grid">
            <div class="metric-box">
                <div class="metric-value">{{ incident.root_cause_device }}</div>
                <div class="metric-label">Root Cause Device</div>
            </div>
            <div class="metric-box">
                <div class="metric-value">{{ incident.confidence }}%</div>
                <div class="metric-label">Confidence Score</div>
            </div>
            <div class="metric-box">
                <div class="metric-value">{{ raw_events_count }} &rarr; {{ unique_alarms_count }} &rarr; 1</div>
                <div class="metric-label">Raw &rarr; Alarms &rarr; Incident</div>
            </div>
            <div class="metric-box">
                <div class="metric-value" style="color: #27ae60;">{{ "%.1f"|format(noise_reduction_pct) }}%</div>
                <div class="metric-label">Noise Reduction</div>
            </div>
        </div>

        <div class="section">
            <div class="section-title">Executive Summary</div>
            <div class="summary-card">
                <p>
                    A <strong>{{ incident.severity.value }}</strong> severity incident originated at 
                    <strong>{{ incident.root_cause_device }}</strong> starting at <code>{{ incident.start_time.strftime('%Y-%m-%d %H:%M:%S') }}</code>. 
                    Root Cause Analysis identified: <em>{{ incident.probable_cause }}</em> with <strong>{{ incident.confidence }}%</strong> diagnostic confidence. 
                    A total of <strong>{{ incident.secondary_alarms|length }}</strong> secondary alarms were correlated and suppressed, preventing operational alert fatigue.
                </p>
            </div>
        </div>

        <div class="section">
            <div class="section-title">Correlated Event Breakdown</div>
            <table>
                <thead>
                    <tr>
                        <th>Device</th>
                        <th>Event Type</th>
                        <th>Severity</th>
                        <th>Role</th>
                        <th>Occurrences</th>
                        <th>First Seen</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td><strong>{{ incident.primary_alarm.source_device }}</strong></td>
                        <td>{{ incident.primary_alarm.event_type.value }}</td>
                        <td><span class="badge badge-{{ incident.primary_alarm.severity.value }}">{{ incident.primary_alarm.severity.value }}</span></td>
                        <td><span class="role-tag role-{{ incident.primary_alarm.role.value }}">{{ incident.primary_alarm.role.value }}</span></td>
                        <td>{{ incident.primary_alarm.occurrence_count }}</td>
                        <td>{{ incident.primary_alarm.first_seen.strftime('%H:%M:%S') }}</td>
                    </tr>
                    {% for alarm in incident.secondary_alarms %}
                    <tr>
                        <td>{{ alarm.source_device }}</td>
                        <td>{{ alarm.event_type.value }}</td>
                        <td><span class="badge badge-{{ alarm.severity.value }}">{{ alarm.severity.value }}</span></td>
                        <td><span class="role-tag role-{{ alarm.role.value }}">{{ alarm.role.value }}</span></td>
                        <td>{{ alarm.occurrence_count }}</td>
                        <td>{{ alarm.first_seen.strftime('%H:%M:%S') }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>

        <div class="section">
            <div class="section-title">Impact Analysis (Affected Topology)</div>
            <p style="font-size: 14px;">The following <strong>{{ incident.affected_devices|length }}</strong> downstream devices were impacted or isolated by this root failure:</p>
            <div style="background: #f8f9fa; border: 1px solid #e9ecef; padding: 12px; border-radius: 6px; font-family: monospace; font-size: 13px;">
                {{ incident.affected_devices | join(', ') }}
            </div>
        </div>

        <div class="section">
            <div class="section-title">Recommended Remediation Steps</div>
            <ol class="remediation-list">
                {% for rec in incident.recommendations %}
                <li>{{ rec }}</li>
                {% endfor %}
            </ol>
        </div>

        <div class="footer">
            Automated Report generated by NMS Fault Detection & RCA Engine &bull; {{ generated_at }}
        </div>
    </div>
</body>
</html>
"""


class ReportGenerator:
    def __init__(self, topology: Optional[NetworkTopology] = None):
        self.topology = topology
        self.template = Template(HTML_TEMPLATE)

    def generate_html_report(
        self,
        incident: Incident,
        raw_events_count: int = 100,
        unique_alarms_count: int = 10,
        noise_reduction_pct: float = 90.0
    ) -> str:
        """Render complete HTML report for an Incident."""
        return self.template.render(
            incident=incident,
            raw_events_count=raw_events_count,
            unique_alarms_count=unique_alarms_count,
            noise_reduction_pct=noise_reduction_pct,
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
