import datetime
import hashlib
import json
import sqlite3
from collections import Counter

import requests
from flask import Flask, jsonify, render_template_string

# ==========================================
# CONFIGURATION
# ==========================================
DB_FILE = 'ecfr_data.db'
URL_AGENCIES = "https://www.ecfr.gov/api/admin/v1/agencies.json"
URL_CORRECTIONS = "https://www.ecfr.gov/api/admin/v1/corrections.json"

app = Flask(__name__)


# ==========================================
# DATABASE LAYER (Server-Side Storage)
# ==========================================
def init_db():
    """Initializes the local SQLite database."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    # Table for Agencies
    c.execute('''CREATE TABLE IF NOT EXISTS agencies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT,
                    short_name TEXT,
                    raw_data TEXT,
                    checksum TEXT
                )''')

    # Table for Corrections
    c.execute('''CREATE TABLE IF NOT EXISTS corrections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agency_id INTEGER,
                    correction_date TEXT,
                    title TEXT,
                    raw_data TEXT
                )''')

    conn.commit()
    conn.close()


def save_data(agencies, corrections):
    """Stores downloaded data into the database."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    # 1. Clear old data
    c.execute("DELETE FROM agencies")
    c.execute("DELETE FROM corrections")

    # 2. Insert Agencies
    agency_list = agencies.get('agencies', []) if isinstance(agencies, dict) else agencies

    for agency in agency_list:
        agency_str = json.dumps(agency, sort_keys=True)
        checksum = hashlib.md5(agency_str.encode('utf-8')).hexdigest()

        c.execute(
            "INSERT INTO agencies (name, short_name, raw_data, checksum) VALUES (?, ?, ?, ?)",
            (agency.get('name'), agency.get('short_name'), agency_str, checksum)
        )

    # 3. Insert Corrections
    # Extraction: API structure can vary
    correction_list = []
    if isinstance(corrections, dict):
        if 'ecfr_corrections' in corrections:
            correction_list = corrections['ecfr_corrections']
        elif 'corrections' in corrections:
            correction_list = corrections['corrections']
        else:
            # Try to find any list in the values
            for v in corrections.values():
                if isinstance(v, list):
                    correction_list = v
                    break
    elif isinstance(corrections, list):
        correction_list = corrections

    if correction_list:
        # Debug: to help troubleshoot in console
        try:
            print(f"DEBUG: Sample Correction Keys found: {list(correction_list[0].keys())}")
        except Exception:
            pass

    count_corrections = 0
    for corr in correction_list:
        corr_str = json.dumps(corr)

        # Date Extraction: Try multiple common API date keys
        eff_date = (corr.get('effective_on') or
                    corr.get('publication_date') or
                    corr.get('date') or
                    corr.get('last_modified') or
                    corr.get('error_corrected_on'))

        # Title Extraction
        title = (corr.get('title') or
                 corr.get('short_title') or
                 corr.get('name') or
                 "Untitled Correction")

        if eff_date:
            c.execute(
                "INSERT INTO corrections (correction_date, title, raw_data) VALUES (?, ?, ?)",
                (eff_date, title, corr_str)
            )
            count_corrections += 1

    conn.commit()
    conn.close()
    print(f"DEBUG: Saved {count_corrections} corrections to DB.")


def get_stats():
    """Retrieves data for analysis."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # Get Agencies - Convert to dict
    agencies_rows = c.execute("SELECT name, short_name, checksum FROM agencies").fetchall()
    agencies = [dict(row) for row in agencies_rows]

    # Get Corrections - Convert to dict
    corrections_rows = c.execute("SELECT correction_date, title FROM corrections").fetchall()
    corrections = [dict(row) for row in corrections_rows]

    conn.close()
    return agencies, corrections


# ==========================================
# DATA INGESTION (ETL)
# ==========================================
def download_ecfr_data():
    """Downloads data with error handling."""
    data = {"agencies": {}, "corrections": {}}
    errors = []

    # Fetch Agencies
    try:
        r_ag = requests.get(URL_AGENCIES, timeout=15)
        r_ag.raise_for_status()
        data["agencies"] = r_ag.json()
    except requests.exceptions.RequestException as e:
        errors.append(f"Failed to download Agencies: {str(e)}")

    # Fetch Corrections
    try:
        # Ensure to get JSON
        r_corr = requests.get(URL_CORRECTIONS, timeout=20)
        r_corr.raise_for_status()
        data["corrections"] = r_corr.json()
    except requests.exceptions.RequestException as e:
        errors.append(f"Failed to download Corrections: {str(e)}")

    return data, errors


# ==========================================
# FLASK API ROUTES
# ==========================================
@app.route('/api/refresh', methods=['POST'])
def refresh_data():
    """API endpoint to trigger data download and storage."""
    data, errors = download_ecfr_data()

    # If both failed, return error messages
    if not data["agencies"] and not data["corrections"]:
        return jsonify({"status": "error", "errors": errors}), 500

    try:
        save_data(data["agencies"], data["corrections"])
        return jsonify({
            "status": "success",
            "message": "Data downloaded and stored successfully.",
            "errors": errors
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/analysis', methods=['GET'])
def get_analysis():
    """API endpoint returning analyzed metrics."""
    try:
        rows_agencies, rows_corrections = get_stats()

        # Metric 1: Word Count per Agency
        agency_metrics = []
        for ag in rows_agencies:
            name_len = len(ag['name'].split()) if ag.get('name') else 0
            agency_metrics.append({
                "name": ag['name'],
                "short_name": ag['short_name'],
                "word_count": name_len,
                "checksum": ag['checksum']
            })

        # Metric 2: Historical Changes
        # Filter for valid dates and strings only
        dates = [c['correction_date'] for c in rows_corrections if c.get('correction_date')]
        dates.sort()

        # Group by Year-Month (YYYY-MM)
        # Handle dates like "2023-05-15" or "2023-05-15T10:00:00"
        valid_dates = []
        for d in dates:
            if d and len(str(d)) >= 7:
                valid_dates.append(str(d)[:7])

        history = Counter(valid_dates)

        # Metric 3 (CUSTOM): "Correction Volatility"
        years = [d[:4] for d in valid_dates]
        year_counts = Counter(years)
        most_volatile_year = year_counts.most_common(1)[0] if year_counts else ("None", 0)

        custom_metric = {
            "name": "Most Volatile Year",
            "description": "The year with the highest volume of corrections.",
            "year": most_volatile_year[0],
            "count": most_volatile_year[1]
        }

        return jsonify({
            "agency_analysis": agency_metrics,  # Return ALL agencies, let JS handle search
            "history": dict(history),
            "custom_metric": custom_metric,
            "total_agencies": len(agency_metrics),
            "total_corrections": len(rows_corrections)
        })
    except Exception as e:
        print(f"Error in analysis: {e}")
        return jsonify({"error": str(e)}), 500


# ==========================================
# UI (Frontend)
# ==========================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>eCFR Data Analyzer</title>
    <style>
        body { font-family: -apple-system, sans-serif; max-width: 1000px; margin: 0 auto; padding: 20px; background: #f4f4f9; }
        .card { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 20px; }
        button { background: #007bff; color: white; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer; }
        button:hover { background: #0056b3; }
        button:disabled { background: #ccc; }
        table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        th, td { text-align: left; padding: 8px; border-bottom: 1px solid #ddd; }
        th { background-color: #f8f9fa; }
        .metric-box { display: inline-block; background: #e9ecef; padding: 10px; border-radius: 4px; margin-right: 10px; }
        h1 { color: #333; margin: 0; }
        pre { background: #333; color: #fff; padding: 10px; border-radius: 4px; overflow-x: auto; }

        /* Flex header styling */
        .header-container {
            display: flex;
            justify-content: space-between;
            align-items: flex-start; /* Changed to align items to top */
            margin-bottom: 30px;
        }

        /* Search Input Styling */
        #searchInput {
            width: 100%;
            padding: 12px;
            margin: 10px 0;
            border: 1px solid #ddd;
            border-radius: 4px;
            box-sizing: border-box;
            font-size: 16px;
        }

        /* Line Chart Styling (SVG) */
        .chart-scroll-wrapper {
            overflow-x: auto;
            padding-bottom: 10px;
            border-bottom: 1px solid #e0e0e0;
        }
        svg.line-chart {
            display: block;
        }
        .chart-line {
            fill: none;
            stroke: #28a745;
            stroke-width: 2;
            stroke-linejoin: round;
            stroke-linecap: round;
        }
        .chart-point {
            fill: #fff;
            stroke: #28a745;
            stroke-width: 2;
            cursor: pointer;
            transition: all 0.2s;
        }
        .chart-point:hover {
            fill: #28a745;
            r: 5;
        }
        .chart-label {
            font-size: 10px;
            fill: #666;
            text-anchor: end;
        }
        .chart-val-label {
            font-size: 9px;
            fill: #333;
            text-anchor: middle;
            font-weight: bold;
        }
    </style>
</head>
<body>

    <div class="header-container">
        <div>
            <h1>eCFR Regulatory Analyzer</h1>
            <p style="margin: 5px 0 0 0; color: #666; font-size: 0.95em;">An online tool for analyzing federal regulations to support deregulation efforts</p>
        </div>
        <div style="text-align: right; min-width: 200px; margin-top: 5px;">
            <span id="status" style="margin-right: 10px; font-weight: bold; font-size: 0.9em;"></span>
            <button id="syncBtn" onclick="syncData()">Download & Sync Data</button>
        </div>
    </div>

    <div class="card">
        <h2>1. Executive Summary</h2>
        <div id="customMetric">
            <em>Load data to see metrics...</em>
        </div>
    </div>

    <!-- Agency Analysis & Search -->
    <div class="card">
        <h2>2. Agency Analysis & Search</h2>
        <p>Search for agencies by <strong>Short Name</strong> (e.g., "EPA", "DHS") or Full Name.</p>

        <input type="text" id="searchInput" onkeyup="filterTable()" placeholder="Search for names (e.g., EPA)...">

        <div style="max-height: 400px; overflow-y: auto;">
            <table id="agencyTable">
                <thead>
                    <tr>
                        <th style="width: 15%">Short Name</th>
                        <th style="width: 15%">Word Count</th>
                        <th style="width: 35%">Agency Name</th>
                        <th style="width: 35%">Data Checksum</th>
                    </tr>
                </thead>
                <tbody></tbody>
            </table>
        </div>
        <p id="rowCount" style="color: #666; font-size: 0.9em; text-align: right;"></p>
    </div>

    <!-- Historical Corrections (Line Chart) -->
    <div class="card">
        <h2>3. Historical Corrections</h2>
        <p>Corrections over time (YYYY-MM):</p>
        <div id="historyChart">
            <em>Chart will appear here after data sync.</em>
        </div>
    </div>

    <script>
        // Global store for agencies to allow client-side filtering
        let allAgencies = [];

        async function syncData() {
            const btn = document.getElementById('syncBtn');
            const status = document.getElementById('status');
            btn.disabled = true;
            status.textContent = "Downloading...";

            try {
                const res = await fetch('/api/refresh', { method: 'POST' });
                const data = await res.json();
                if (data.status === 'success') {
                    status.textContent = "Success!";
                    status.style.color = "green";
                    loadStats();
                } else {
                    status.textContent = "Error: " + (data.message || "Unknown error");
                    status.style.color = "red";
                }
            } catch (e) {
                status.textContent = "Network Error";
            } finally {
                btn.disabled = false;
            }
        }

        async function loadStats() {
            try {
                const res = await fetch('/api/analysis');
                const data = await res.json();

                if (data.error) {
                    console.error(data.error);
                    return;
                }

                // 1. Render Custom Metric
                const metricDiv = document.getElementById('customMetric');
                metricDiv.innerHTML = `
                    <div class="metric-box">
                        <strong>Total Agencies</strong><br>${data.total_agencies}
                    </div>
                    <div class="metric-box">
                        <strong>Total Corrections</strong><br>${data.total_corrections}
                    </div>
                    <div class="metric-box" style="border-left: 3px solid navy; color: navy;">
                        <strong>${data.custom_metric.name}</strong><br>
                        ${data.custom_metric.year} (${data.custom_metric.count} corrections)
                    </div>
                `;

                // 2. Render History (Line Chart using SVG)
                const histDiv = document.getElementById('historyChart');
                const sortedKeys = Object.keys(data.history).sort();

                if (sortedKeys.length === 0) {
                    histDiv.innerHTML = '<p style="color: #666;">No historical correction data found.</p>';
                } else {
                    const counts = Object.values(data.history);
                    const maxVal = Math.max(...counts, 1);

                    // Chart Dimensions
                    const height = 250;
                    const topPadding = 20;
                    const bottomPadding = 60; // Space for rotated labels
                    const sidePadding = 30;
                    const pointGap = 40; // Horizontal space between points

                    // Total width depends on data points, min 800
                    const width = Math.max(800, sortedKeys.length * pointGap + sidePadding * 2);
                    const graphHeight = height - bottomPadding;

                    let polylinePoints = '';
                    let pointsHtml = '';
                    let labelsHtml = '';

                    sortedKeys.forEach((k, index) => {
                        const count = data.history[k];

                        // Calculate Coordinates
                        const x = sidePadding + (index * pointGap);
                        // Invert Y (SVG 0 is top) + scaling
                        const relativeHeight = (count / maxVal) * (graphHeight - topPadding);
                        const y = graphHeight - relativeHeight;

                        // Add to polyline
                        polylinePoints += `${x},${y} `;

                        // Add Point Circle
                        pointsHtml += `<circle cx="${x}" cy="${y}" r="3" class="chart-point">
                            <title>Date: ${k}\\nCorrections: ${count}</title>
                        </circle>`;

                        // Add X-Axis Label (Rotated 45 degrees)
                        // Transform rotates around the text position
                        labelsHtml += `<text x="${x}" y="${height - 45}" class="chart-label" transform="rotate(-45, ${x}, ${height - 45})">${k}</text>`;

                        // Add value text above point for ALL dates
                        labelsHtml += `<text x="${x}" y="${y - 8}" class="chart-val-label">${count}</text>`;
                    });

                    const svgHTML = `
                        <div class="chart-scroll-wrapper">
                            <svg class="line-chart" width="${width}" height="${height}">
                                <!-- Y-Axis Line -->
                                <line x1="${sidePadding}" y1="${topPadding}" x2="${sidePadding}" y2="${graphHeight}" stroke="#ddd" stroke-width="1" />
                                <!-- X-Axis Line -->
                                <line x1="${sidePadding}" y1="${graphHeight}" x2="${width}" y2="${graphHeight}" stroke="#ddd" stroke-width="1" />

                                <!-- The Data Line -->
                                <polyline points="${polylinePoints}" class="chart-line" />

                                <!-- Labels & Points -->
                                ${labelsHtml}
                                ${pointsHtml}
                            </svg>
                        </div>
                    `;

                    histDiv.innerHTML = svgHTML;
                }

                // 3. Store Agencies globally and render initial table
                allAgencies = data.agency_analysis;
                renderTable(allAgencies);

            } catch (e) {
                console.error(e);
            }
        }

        function renderTable(data) {
            const tbody = document.querySelector('#agencyTable tbody');
            const countDisplay = document.getElementById('rowCount');

            tbody.innerHTML = '';

            if (data.length === 0) {
                tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;">No matching agencies found.</td></tr>';
                countDisplay.textContent = '0 records';
                return;
            }

            data.forEach(ag => {
                const shortName = ag.short_name || "-";
                const row = `<tr>
                    <td><strong>${shortName}</strong></td>
                    <td>${ag.word_count}</td>
                    <td>${ag.name}</td>
                    <td style="font-family: monospace; font-size: 0.8em; white-space: nowrap;">${ag.checksum}</td>
                </tr>`;
                tbody.innerHTML += row;
            });

            countDisplay.textContent = `Showing ${data.length} records`;
        }

        function filterTable() {
            const input = document.getElementById('searchInput');
            const filter = input.value.toUpperCase();

            if (!allAgencies.length) return;

            const filteredData = allAgencies.filter(ag => {
                const name = ag.name ? ag.name.toUpperCase() : "";
                const short = ag.short_name ? ag.short_name.toUpperCase() : "";

                // Search in both Name and Short Name
                return name.indexOf(filter) > -1 || short.indexOf(filter) > -1;
            });

            renderTable(filteredData);
        }

        // Try load on refresh
        loadStats();
    </script>
</body>
</html>
"""


@app.route('/')
def home():
    return render_template_string(HTML_TEMPLATE)


# ==========================================
# MAIN ENTRY POINT
# ==========================================
if __name__ == '__main__':
    init_db()
    print("Server running. Access UI at http://127.0.0.1:5000")
    app.run(debug=True, port=5000)
