"""
CertifyFlow - Streamlit Bulk Certificate Studio
Interactive Python UI for dispatching jobs and monitoring real-time generation progress.
"""

import io
import time
import datetime
import requests
import pandas as pd
import streamlit as st

# --- Streamlit Page Configuration ---
st.set_page_config(
    page_title="CertifyFlow | Bulk Certificate Studio",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Custom Styling ---
st.markdown(
    """
    <style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 800;
        letter-spacing: -0.02em;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1rem;
        color: #94a3b8;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background-color: rgba(30, 41, 59, 0.4);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 8px;
        padding: 1rem;
        text-align: center;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- Sidebar Configuration ---
with st.sidebar:
    st.title("⚙️ Cluster Settings")
    st.markdown("Configure target API gateway and security credentials.")

    api_base_url = st.text_input(
        "API Base URL",
        value="http://127.0.0.1:8000",
        help="FastAPI server address",
    ).rstrip("/")

    api_key = st.text_input(
        "API Key (X-API-Key)",
        value="dev-secret-key-12345",
        type="password",
        help="Master security key required for /api/v1/* routes",
    )

    st.markdown("---")
    st.subheader("Cluster Health")

    # Live Health Check
    try:
        health_resp = requests.get(f"{api_base_url}/healthz", timeout=3)
        if health_resp.status_code == 200:
            h_data = health_resp.json()
            storage_backend = h_data.get("checks", {}).get("storage", {}).get("backend", "local").upper()
            st.success(f"Cluster Operational (Storage: {storage_backend})")
        else:
            st.warning(f"Cluster Degraded (Status {health_resp.status_code})")
    except Exception as exc:
        st.error(f"Cannot reach API: {exc}")

    st.markdown("---")
    st.markdown(f"[📖 Interactive OpenAPI Docs]({api_base_url}/docs)")
    st.markdown(f"[🖥️ Web Studio Dashboard]({api_base_url}/dashboard)")

# --- Main App Header ---
st.markdown('<div class="main-header">Bulk Certificate <span style="color:#6366f1;">Studio</span></div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-header">Dispatch enterprise batches of certificate recipients to Celery background workers with real-time streaming updates.</div>',
    unsafe_allow_html=True,
)

# --- Form Inputs ---
col_course, col_date = st.columns([3, 1])

with col_course:
    course_name = st.text_input(
        "Course / Credential Title *",
        value="Advanced Cloud Architecture & Distributed Systems",
        placeholder="e.g. Machine Learning Specialization",
    )

with col_date:
    issue_date = st.date_input("Issue Date *", value=datetime.date.today())

st.markdown("### 📋 Recipient Roster")

input_mode = st.radio(
    "Choose Recipient Input Method:",
    options=["Interactive Table Editor", "Upload CSV File"],
    horizontal=True,
)

recipients_list = []

if input_mode == "Interactive Table Editor":
    st.caption("Add, edit, or remove recipients directly in the table below:")
    default_data = [
        {"Name": "Alice Smith", "Email": "alice.smith@enterprise.io"},
        {"Name": "Bob Jones", "Email": "bob.jones@architecture.dev"},
        {"Name": "Charlie Brown", "Email": "charlie.brown@devops.org"},
        {"Name": "Diana Prince", "Email": "diana.prince@engineering.net"},
        {"Name": "Evan Wright", "Email": "evan.wright@scalabletech.com"},
    ]
    df_input = pd.DataFrame(default_data)
    edited_df = st.data_editor(
        df_input,
        num_rows="dynamic",
        use_container_width=True,
        key="recipients_editor",
    )

    for _, row in edited_df.iterrows():
        name = str(row.get("Name", "")).strip()
        email = str(row.get("Email", "")).strip()
        if name and email and name.lower() != "nan" and email.lower() != "nan":
            recipients_list.append({"name": name, "email": email})

else:
    st.caption("Upload a CSV file containing `name` and `email` columns (or first two columns):")
    uploaded_file = st.file_uploader("Upload CSV", type=["csv", "txt"])
    if uploaded_file is not None:
        try:
            csv_df = pd.read_csv(uploaded_file)
            st.write("Uploaded Preview:", csv_df.head(5))
            if "name" in csv_df.columns and "email" in csv_df.columns:
                for _, row in csv_df.iterrows():
                    name = str(row["name"]).strip()
                    email = str(row["email"]).strip()
                    if name and email:
                        recipients_list.append({"name": name, "email": email})
            elif len(csv_df.columns) >= 2:
                for _, row in csv_df.iterrows():
                    name = str(row.iloc[0]).strip()
                    email = str(row.iloc[1]).strip()
                    if name and email:
                        recipients_list.append({"name": name, "email": email})
            st.info(f"Loaded {len(recipients_list)} recipients from CSV.")
        except Exception as e:
            st.error(f"Error reading CSV: {e}")

st.write(f"**Total Valid Recipients Ready:** `{len(recipients_list)}`")

# --- Submit Action ---
if st.button("🚀 Generate Certificates", type="primary", use_container_width=True):
    if not course_name.strip():
        st.error("Please specify a course title.")
    elif len(recipients_list) == 0:
        st.error("Please add at least one recipient with valid name and email.")
    else:
        payload = {
            "course_name": course_name.strip(),
            "issue_date": str(issue_date),
            "recipients": recipients_list,
        }

        headers = {
            "Content-Type": "application/json",
            "X-API-Key": api_key,
        }

        try:
            with st.spinner("Submitting batch job to API..."):
                response = requests.post(
                    f"{api_base_url}/api/v1/jobs/",
                    json=payload,
                    headers=headers,
                    timeout=10,
                )

            if response.status_code == 429:
                st.error("Rate limit exceeded (5 requests per minute). Please try again shortly.")
            elif response.status_code == 401:
                st.error("Unauthorized: Please verify your API Key in the sidebar.")
            elif response.status_code != 202:
                st.error(f"API Error ({response.status_code}): {response.text}")
            else:
                job_data = response.json()
                job_id = job_data["job_id"]
                st.success(f"Job Dispatched Successfully! Job ID: `{job_id}`")

                # Store active job in session state
                st.session_state["active_job_id"] = job_id

        except Exception as exc:
            st.error(f"Failed to submit job: {exc}")

# --- Monitoring & Results Section ---
if "active_job_id" in st.session_state:
    active_id = st.session_state["active_job_id"]
    st.markdown("---")
    st.subheader(f"📊 Live Job Monitor: `{active_id}`")

    headers = {"X-API-Key": api_key}
    progress_bar = st.progress(0.0)
    status_text = st.empty()

    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    metric_total = col_m1.empty()
    metric_success = col_m2.empty()
    metric_failed = col_m3.empty()
    metric_status = col_m4.empty()

    is_complete = False
    max_polls = 120  # Max ~2 minutes polling
    poll_count = 0

    while not is_complete and poll_count < max_polls:
        poll_count += 1
        try:
            status_resp = requests.get(
                f"{api_base_url}/api/v1/jobs/{active_id}",
                headers=headers,
                timeout=5,
            )
            if status_resp.status_code == 200:
                s_data = status_resp.json()
                pct = float(s_data.get("progress_percent", 0.0)) / 100.0
                progress_bar.progress(min(pct, 1.0))

                job_status = s_data.get("status")
                metric_total.metric("Total Records", s_data.get("total", 0))
                metric_success.metric("Succeeded", s_data.get("succeeded", 0))
                metric_failed.metric("Failed", s_data.get("failed", 0))
                metric_status.metric("Job Status", job_status)

                status_text.write(f"Status: **{job_status}** ({s_data.get('progress_percent')}%)")

                if job_status in ["COMPLETED", "COMPLETED_WITH_ERRORS", "FAILED"]:
                    is_complete = True
                    break
            else:
                status_text.warning(f"Polling warning: Status {status_resp.status_code}")
        except Exception as e:
            status_text.error(f"Polling error: {e}")

        time.sleep(1.0)

    # --- Certificates Table & Download Actions ---
    try:
        certs_resp = requests.get(
            f"{api_base_url}/api/v1/jobs/{active_id}/certificates?page=1&page_size=100",
            headers=headers,
            timeout=5,
        )
        if certs_resp.status_code == 200:
            certs_data = certs_resp.json().get("items", [])
            if certs_data:
                st.markdown("### 📜 Generated Certificates")
                table_rows = []
                for c in certs_data:
                    table_rows.append({
                        "Recipient Name": c.get("recipient_name"),
                        "Email": c.get("recipient_email"),
                        "Status": c.get("status"),
                        "Error Details": c.get("error_message") or "-",
                        "Certificate ID": c.get("id"),
                    })
                df_results = pd.DataFrame(table_rows)
                st.dataframe(df_results, use_container_width=True)

                # Download ZIP Action
                succeeded_count = sum(1 for c in certs_data if c.get("status") == "SUCCESS")
                if succeeded_count > 0:
                    st.markdown("#### 📦 Bulk Download")
                    try:
                        zip_resp = requests.get(
                            f"{api_base_url}/api/v1/jobs/{active_id}/download",
                            headers=headers,
                            timeout=30,
                        )
                        if zip_resp.status_code == 200:
                            st.download_button(
                                label=f"⬇️ Download All {succeeded_count} Certificates (.ZIP)",
                                data=zip_resp.content,
                                file_name=f"certificates_job_{active_id}.zip",
                                mime="application/zip",
                                type="primary",
                            )
                        else:
                            st.warning("ZIP archive is being generated...")
                    except Exception as ze:
                        st.error(f"Failed to fetch ZIP archive: {ze}")

    except Exception as err:
        st.error(f"Failed loading certificates: {err}")
