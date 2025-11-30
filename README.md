# eCFR_python
This is the repo to keep eCFR python codes submitted to USDS

**eCFR Regulatory Analyzer**

A self-contained Python web application designed to download, analyze and visualize federal regulation data from the [eCFR.gov] APIs. This tool helps support deregulation efforts by providing insights into agency complexity and regulatory volatility.

**Features**

- **Automated Data Ingestion:** Downloads fresh data for Federal Agencies and Corrections directly from eCFR APIs.

- **Server-Side Storage:** Persists data locally using a lightweight SQLite database (**ecfr_data.db**), ensuring analysis is available without constant API calls.

- **Interactive Dashboard:**

  - **Executive Summary:** Highlights key metrics, including a custom \"Most Volatile Year\" indicator.

  - **Agency Search & Analysis:** A searchable table displaying Agency names, short names, name complexity (word count), and data integrity    checksums.

  - **Historical Trends:** A dynamic line chart visualizing the volume of regulatory corrections over time.

- **Error Handling:** Includes retry logic and user-friendly status messages for network operations.

**Project Structure**

This is a single-file application (**ecfr_analyzer.py**) which contains:

- **Database Layer:** SQLite initialization and schema management.

- **ETL Layer:** Logic to fetch and normalize data from eCFR.

- **Flask Backend:** Routes for serving the UI and API data.

- **Frontend:** Embedded HTML/CSS/JavaScript for the dashboard.
  
**Prerequisites**

- Python 3.6+

- pip (Python package installer)

**Installation**

1.  **Clone or download** the repository containing ecfr_analyzer.py.

2.  **Install Dependencies:** You need Flask for the web server and requests for fetching API data.

3.  pip install flask requests

**Usage**

1.  **Run the Script:** Navigate to the directory containing the script, run and leave it running.  This will start Serving Flask app ecfr_analyzer'.  Do not press CTRL+C.

2.  python ecfr_analyzer.py

3.  **Access the Application:** Open your web browser and go to: http://127.0.0.1:5000

4.  **Sync Data:**

    - On the dashboard, click the **\"Download & Sync Data\"** button in the top right corner.

    - Wait for the \"Success!\" message. This populates the local database.

**Testing**

To verify the application is working correctly, perform the following manual tests:

1.  **Startup Verification:** Run the script and ensure the console prints Server running. Access UI at http://127.0.0.1:5000.

2.  **Database Creation:** After the first run, check the project directory to ensure the file ecfr_data.db has been created.

3.  **Data Sync:**

    - Click the \"Download & Sync Data\" button.

    - **Success Criteria:** The status text changes to
      \"Downloading\...\", then \"Success!\" in green. The charts and tables populate immediately.

    - **Failure Criteria:** If the status turns red, check the terminal window for python error logs.

4.  **Search Functionality:** Type \"EPA\" or \"Environment\" into the search bar. The table should filter rows dynamically to show only relevant agencies.

5.  **Chart Interaction:** Hover over the white dots on the \"Historical Corrections\" line chart. A tooltip should appear displaying the specific date and correction count.

**Troubleshooting**

Common posible issues and their solutions:

**1. OSError: \[Errno 98\] Address already in use**

- **Cause:** Another instance of the script (or another application) is already using port 5000.

- **Fix:** Stop the other process or modify the app.run(port=5000) line in the script to use a different port (e.g., port=5001).

**2. Network Errors / \"Failed to download\...\"**

- **Cause:** The application cannot reach ecfr.gov due to internet issues or API downtime.

- **Fix:**

  - Verify your internet connection.

  - Check if https://www.ecfr.gov/api/admin/v1/agencies.json loads in your browser.

  - If the API is slow, you may need to increase the timeout=15 value in the download_ecfr_data function.

**3. \"No historical correction data found\"**

- **Cause:** The API response format may have changed, or the database is empty.

- **Fix:** Check the python console logs. The script includes debug
  prints (e.g., DEBUG: Sample Correction Keys found\...) that show exactly what data keys are being received.

**4. sqlite3.OperationalError: database is locked**

- **Cause:** Two processes are trying to write to ecfr_data.db simultaneously, or the script crashed while writing.

- **Fix:** Stop the python script. Delete the ecfr_data.db file (it will be recreated automatically on the next run). Restart the script.

**API Endpoints**

The application exposes two internal API endpoints used by the frontend:

- **POST /api/refresh**: Triggers the download of JSON data from eCFR and updates the SQLite database.

- **GET /api/analysis**: Returns aggregated statistics, historical trends, and agency lists in JSON format.

  [eCFR.gov]: https://www.ecfr.gov/


