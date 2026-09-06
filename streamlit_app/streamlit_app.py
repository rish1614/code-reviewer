"""
Nightshift — The 24/7 Intelligent Code Reviewer (Streamlit frontend)

Talks to the existing FastAPI backend (app/main.py) over HTTP.
Run locally:
    streamlit run streamlit_app.py

Set the backend URL via an environment variable so the same code works
locally and once deployed to Cloud Run:
    API_BASE=http://localhost:8080 streamlit run streamlit_app.py
"""

import os
import requests
import streamlit as st

API_BASE = os.getenv("API_BASE", "http://localhost:8080")

st.set_page_config(
    page_title="Nightshift — The 24/7 Intelligent Code Reviewer",
    page_icon=">_",
    layout="wide",
)

st.markdown(
    """
    <style>
        .stApp { background-color: #14161a; }
        h1, h2, h3, p, label, span { color: #e6e8eb !important; }
        .stTextArea textarea { font-family: monospace; background-color: #101215; color: #e6e8eb; }
        .rating-box { font-size: 40px; font-weight: 700; color: #7fd1ae; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title(">_ Nightshift")
st.caption("the 24/7 intelligent code reviewer — analyzed by Gemini, grounded in historical review rules")

col1, col2 = st.columns([1.3, 1])

# ---------------- Left column: submission ----------------
with col1:
    st.subheader("Submit code for review")
    language = st.selectbox(
        "Language",
        ["python", "javascript", "typescript", "java", "go", "c++", "sql"],
    )
    code = st.text_area("Paste a function, file, or diff to review...", height=300)

    run_clicked = st.button("Run review", type="primary")

# ---------------- Right column: result ----------------
with col2:
    st.subheader("Review result")
    st.caption("Quality rating on a 1–10 scale")

    if run_clicked:
        if not code.strip():
            st.warning("Paste some code first.")
        else:
            with st.spinner("Analyzing with Gemini..."):
                try:
                    resp = requests.post(
                        f"{API_BASE}/api/v1/reviews",
                        json={"language": language, "code": code},
                        timeout=60,
                    )
                    resp.raise_for_status()
                    data = resp.json()

                    st.markdown(
                        f"<div class='rating-box'>{data['quality_rating']} / 10</div>",
                        unsafe_allow_html=True,
                    )
                    st.markdown("**bug report**")
                    st.write(data["bug_report"])
                    st.markdown("**best practices**")
                    st.write(data["best_practices"])
                    st.markdown("**optimization notes**")
                    st.write(data["optimization_notes"])

                    if data.get("matched_rules"):
                        st.markdown("**grounded in historical rules**")
                        st.write(", ".join(f"rule #{r}" for r in data["matched_rules"]))

                    st.success("Review complete.")
                except requests.exceptions.RequestException as e:
                    st.error(f"Could not reach the backend: {e}")
    else:
        st.info("Submit code on the left to see a review here.")

st.divider()

# ---------------- Session history ----------------
st.subheader("Session history")
st.caption("Every review is saved so growth and patterns can be tracked over time.")

if st.button("Refresh history"):
    st.session_state["refresh_history"] = True

try:
    hist_resp = requests.get(f"{API_BASE}/api/v1/reviews", timeout=30)
    hist_resp.raise_for_status()
    history = hist_resp.json()

    if not history:
        st.write("No reviews yet.")
    else:
        for item in history:
            c1, c2 = st.columns([4, 1])
            c1.write(f"#{item['id']} · {item['language']} · {item['created_at']}")
            c2.write(f"**{item['quality_rating']}/10**")
except requests.exceptions.RequestException as e:
    st.write(f"Could not load history: {e}")

st.divider()

# ---------------- Historical rules ingestion ----------------
st.subheader("Historical rules dataset")
st.caption("Upload the CSV (id, type, description) used to ground future reviews.")

uploaded_file = st.file_uploader("Choose CSV file", type=["csv"])
if st.button("Ingest CSV"):
    if uploaded_file is None:
        st.warning("Choose a CSV file first.")
    else:
        with st.spinner("Embedding and ingesting rules..."):
            try:
                files = {"file": (uploaded_file.name, uploaded_file.getvalue(), "text/csv")}
                ingest_resp = requests.post(
                    f"{API_BASE}/api/v1/historical-rules/ingest", files=files, timeout=60
                )
                ingest_resp.raise_for_status()
                st.success(ingest_resp.json()["message"])
            except requests.exceptions.RequestException as e:
                st.error(f"Could not reach the backend: {e}")

st.divider()
st.caption("Deployed on Cloud Run · Gemini via Vertex AI · Cloud SQL · Identity Platform")
