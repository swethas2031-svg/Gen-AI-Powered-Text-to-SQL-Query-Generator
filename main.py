import os
import re
import sys
import logging
import hashlib

from openai import APIError, OpenAI
import pandas as pd
import streamlit as st
from google.api_core.exceptions import ResourceExhausted
from utils import init_session_state, widget_control
from sqlalchemy import create_engine, inspect
from components.sidebar import sidebar_block
from auth import (
    add_query_history as save_user_query_history,
    clear_query_history,
    get_query_history,
    get_saved_model,
    initialize_auth_state,
    mark_query_has_results,
    render_auth_page,
    render_user_sidebar,
)

process_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

if process_dir not in sys.path:
    sys.path.append(process_dir)

from process.rag_process import Text2SQL

logger = logging.getLogger(__name__)


DEMO_DATA = (
    "employees table with columns:\n"
    "id, name, department, salary, age\n\n"
    "Sample rows:\n"
    "1, Rahul, IT, 55000, 24\n"
    "2, Priya, HR, 45000, 28\n"
    "3, Anjali, IT, 65000, 25\n"
    "4, Aman, Finance, 70000, 30\n"
    "5, Sneha, Sales, 48000, 26"
)
DEMO_QUESTION = "Show employees from the IT department earning more than 50000."
DEMO_SQL = "SELECT * FROM employees WHERE department = 'IT' AND salary > 50000;"

# Every one of these runs entirely locally against the built-in demo dataset —
# no model or API key required, same as the original "Try Demo" button.
DEMO_QA = {
    DEMO_QUESTION: DEMO_SQL,
    "Show all employees": "SELECT * FROM employees;",
    "Find high salary employees": "SELECT * FROM employees WHERE salary > 50000;",
    "Count employees by department": (
        "SELECT department, COUNT(*) AS employee_count FROM employees GROUP BY department;"
    ),
    "Average salary by department": (
        "SELECT department, ROUND(AVG(salary), 2) AS average_salary FROM employees GROUP BY department;"
    ),
}

EXAMPLE_QUESTIONS = [
    "Show all employees",
    "Find high salary employees",
    "Count employees by department",
    "Average salary by department",
]


# ----------------------------------------------------------------------------
# Demo / callback helpers
# ----------------------------------------------------------------------------

def fill_text_sample():
    st.session_state["data_info_text"] = DEMO_DATA
    st.session_state["ask_question"] = DEMO_QUESTION
    st.session_state["data_source"] = "Text Input"
    st.session_state["excel_demo_mode"] = True


def fill_excel_demo():
    st.session_state["data_info_text"] = DEMO_DATA
    st.session_state["ask_question"] = DEMO_QUESTION
    st.session_state["excel_demo_mode"] = True
    st.session_state["data_source"] = "Upload File"


def apply_pill_selection():
    picked = st.session_state.get("quick_pills")
    if picked:
        st.session_state["ask_question"] = picked


def build_excel_demo_text2sql():
    demo_data = pd.DataFrame(
        [
            [1, "Rahul", "IT", 55000, 24],
            [2, "Priya", "HR", 45000, 28],
            [3, "Anjali", "IT", 65000, 25],
            [4, "Aman", "Finance", 70000, 30],
            [5, "Sneha", "Sales", 48000, 26],
        ],
        columns=["id", "name", "department", "salary", "age"],
    )
    text2sql = Text2SQL.__new__(Text2SQL)
    text2sql.engine = create_engine("sqlite:///:memory:")
    text2sql.table_info = "employees table with columns: id, name, department, salary, age"
    demo_data.to_sql("employees", text2sql.engine, if_exists="replace", index=False)
    return text2sql


def get_demo_sql(data_info, question):
    if data_info.strip() != DEMO_DATA:
        return None
    return DEMO_QA.get(question.strip())


def parse_text_schema_counts(data_info):
    if not data_info or not data_info.strip():
        return None, None
    table_matches = re.findall(r"(\w+)\s+table\s+with\s+columns", data_info, flags=re.IGNORECASE)
    tables = len(table_matches) or None
    columns = None
    column_line = re.search(r"columns?:\s*\n?([^\n]+)", data_info, flags=re.IGNORECASE)
    if column_line:
        columns = len([c for c in column_line.group(1).split(",") if c.strip()])
    return tables, columns


def parse_uploaded_files_counts(files):
    if not files:
        return None, None
    tables = len(files)
    columns = 0
    for f in files:
        try:
            f.seek(0)
            if f.name.lower().endswith(".csv"):
                df = pd.read_csv(f, nrows=0)
            else:
                df = pd.read_excel(f, nrows=0)
            columns += len(df.columns)
            f.seek(0)
        except Exception:
            continue
    return tables, columns or None


def refresh_stats_from_engine(engine):
    try:
        inspector = inspect(engine)
        table_names = inspector.get_table_names()
        if table_names:
            st.session_state["stat_tables"] = len(table_names)
            st.session_state["stat_columns"] = sum(
                len(inspector.get_columns(t)) for t in table_names
            )
    except Exception:
        pass


# ----------------------------------------------------------------------------
# Styling — "professional dashboard" theme
# ----------------------------------------------------------------------------

def inject_logged_in_styles():
    st.markdown(
        """
        <style>
        :root {
            --primary: #4f46e5;
            --primary-dark: #4338ca;
            --primary-light: #6366f1;
            --success: #10b981;
            --canvas: #f4f6fb;
            --surface: #ffffff;
            --surface-2: #f5f6fa;
            --ink: #1f2430;
            --muted: #6b7280;
            --line: #e6e9f0;
            --radius: 14px;
            --shadow-sm: 0 1px 2px rgba(16, 24, 40, .04), 0 1px 3px rgba(16, 24, 40, .06);
            --shadow-md: 0 4px 12px rgba(16, 24, 40, .06), 0 2px 4px rgba(16, 24, 40, .04);
        }
        html, body, .stApp { background: var(--canvas); color: var(--ink); font-family: "Inter", "Segoe UI", sans-serif; }
        [data-testid="stMainBlockContainer"] { max-width: 1180px; padding: 3.25rem 2rem 4rem; }
        [data-testid="stHeader"] { background: transparent; }
        h1, h2, h3, h4, p, span, label { color: var(--ink); }

        section[data-testid="stSidebar"] {
            background: #ffffff !important;
            width: 270px !important;
            border-right: 1px solid #e5e7eb;
            box-shadow: 2px 0 12px rgba(15,23,42,0.03);
        }
        section[data-testid="stSidebar"] > div { padding-top: 1.5rem; }
        [data-testid="stSidebarContent"] { padding: 1.1rem 1.15rem; }
        [data-testid="stSidebar"] * { color: var(--ink); }
        [data-testid="stSidebar"] [data-testid="stVerticalBlockBorderWrapper"] { background: transparent !important; border: 0 !important; box-shadow: none !important; }
        [data-testid="stSidebar"] hr {
            margin: 18px 0;
            border-color: #edf0f7;
        }
        [data-testid="stSidebar"] [data-testid="stCaptionContainer"] p,
        [data-testid="stSidebar"] [data-testid="stCaptionContainer"] a {
            color: var(--muted) !important;
            font-size: .68rem;
            line-height: 1.35;
            overflow-wrap: break-word;
            text-decoration: none !important;
        }
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
            color: var(--ink);
            font-size: .85rem;
            line-height: 1.3;
            margin: 4px 0;
        }

        .sidebar-brand {
            display: flex;
            align-items: center;
            color: var(--ink);
            font-size: 1.2rem;
            font-weight: 800;
            padding: 4px 0 18px;
            letter-spacing: -.01em;
        }
        .sidebar-brand-icon {
            color: #ffffff;
            background: linear-gradient(135deg,#2563eb,#7c3aed);
            border-radius: 9px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 30px; height: 30px;
            margin-right: 9px;
            font-size: 16px;
            box-shadow: 0 4px 10px rgba(79,70,229,.3);
        }
        .sidebar-section-label {
            color: #94a3b8;
            font-size: .66rem;
            font-weight: 800;
            letter-spacing: .12em;
            margin: 4px 0 8px;
        }

        [data-testid="stSidebar"] .stRadio [role="radiogroup"] {
            display: flex;
            flex-direction: column;
            gap: 3px;
        }
        [data-testid="stSidebar"] [role="radio"] {
            border-radius: 10px;
            padding: 10px 12px;
            transition: background .15s ease;
        }
        [data-testid="stSidebar"] [role="radio"]:hover { background: #f8fafc; }
        [data-testid="stSidebar"] [role="radio"] p {
            color: #475569 !important;
            font-size: 0.9rem;
        }
        [data-testid="stSidebar"] [role="radio"][aria-checked="true"] {
            background: linear-gradient(90deg,#eef2ff,#f5f3ff);
            border-left: 3px solid #4f46e5;
        }
        [data-testid="stSidebar"] [role="radio"][aria-checked="true"] p {
            color: #4338ca !important;
            font-weight: 700;
        }

        [data-testid="stSidebar"] [data-testid="stPopover"] > button { background: var(--surface-2); border: 1px solid var(--line); border-radius: 10px; color: var(--ink) !important; width: 100%; }
        [data-testid="stSidebar"] [data-testid="stPopover"] > button:hover { border-color: var(--primary); }
        [data-testid="stSidebar"] input, [data-testid="stSidebar"] [data-baseweb="select"] > div { background: var(--surface-2); border-color: var(--line); color: var(--ink); }
        [data-testid="stPopover"] {
            background: var(--surface) !important;
            border: 1px solid var(--line) !important;
            border-radius: 14px !important;
            box-shadow: 0 16px 40px rgba(16, 24, 40, .12) !important;
            min-width: 300px;
            padding: 6px 4px !important;
        }
        [data-testid="stPopover"] [data-testid="stVerticalBlockBorderWrapper"] { padding: 6px 14px 14px; }
        [data-testid="stPopover"] [data-testid="stVerticalBlock"] { gap: .65rem; }
        [data-testid="stPopover"] label p { color: var(--ink) !important; font-size: .85rem; font-weight: 600; margin-bottom: 2px; }
        [data-testid="stPopover"] [role="radiogroup"] { display: flex; gap: 8px; margin: 2px 0 4px; }
        [data-testid="stPopover"] [role="radio"] { background: var(--surface-2); border: 1px solid var(--line); border-radius: 8px; padding: 6px 14px; }
        [data-testid="stPopover"] [role="radio"] p { color: var(--muted) !important; }
        [data-testid="stPopover"] [role="radio"][aria-checked="true"] { background: var(--primary); border-color: var(--primary); }
        [data-testid="stPopover"] [role="radio"][aria-checked="true"] p { color: #ffffff !important; }
        [data-testid="stPopover"] [data-baseweb="select"] > div,
        [data-testid="stPopover"] input {
            background: var(--surface-2) !important;
            border: 1px solid var(--line) !important;
            border-radius: 8px !important;
            color: var(--ink) !important;
        }
        [data-testid="stSidebar"] button[kind="secondary"] { background: var(--surface-2); border: 1px solid var(--line); color: var(--ink) !important; }
        [data-testid="stSidebar"] button[kind="primary"] { background: var(--primary); border-color: var(--primary); }
        [data-testid="stSidebar"] button[kind="primary"], [data-testid="stSidebar"] button[kind="primary"] * { color: #ffffff !important; }

        .sidebar-tip {
            background: linear-gradient(135deg,#f8fafc,#eef2ff);
            border: 1px solid #dbeafe;
            border-radius: 16px;
            margin-top: 16px;
            padding: 14px 16px;
            box-shadow: 0 6px 16px rgba(37,99,235,.06);
        }
        .sidebar-tip-title {
            color: var(--ink);
            font-size: .82rem;
            font-weight: 700;
            margin-bottom: 5px;
        }
        .sidebar-tip-body {
            color: var(--muted);
            font-size: .75rem;
            line-height: 1.5;
        }

        .profile-card {
            margin-top: 22px;
            padding: 16px;
            background: linear-gradient(135deg,#eef2ff,#ffffff);
            border: 1px solid #dbeafe;
            border-radius: 16px;
            box-shadow: 0 8px 24px rgba(79,70,229,.08);
        }
        .profile-avatar {
            width:45px;
            height:45px;
            border-radius:50%;
            background:linear-gradient(135deg,#2563eb,#7c3aed);
            color:white;
            display:flex;
            align-items:center;
            justify-content:center;
            font-weight:700;
            font-size:20px;
            margin-bottom:10px;
        }
        .profile-name {
            font-weight:700;
            color:#111827;
            font-size:15px;
        }
        .profile-email {
            margin-top:4px;
            color:#64748b;
            font-size:12px;
            word-break:break-word;
        }

        .workspace-header { display: flex; align-items: center; justify-content: space-between; margin: 0 0 18px; }
        .workspace-title { color: var(--ink); font-size: 1.6rem; font-weight: 700; margin: 0; letter-spacing: -.01em; }
        .workspace-subtitle { color: var(--muted); font-size: .88rem; margin: 4px 0 0; }

        .dashboard-stat-card {
            background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius);
            min-height: 104px; padding: 16px 18px; box-shadow: var(--shadow-sm);
            transition: border-color .15s ease, transform .15s ease, box-shadow .15s ease;
        }
        .dashboard-stat-card:hover { border-color: #d8dcea; transform: translateY(-2px); box-shadow: var(--shadow-md); }
        .dashboard-stat-icon {
            align-items: center; background: var(--surface-2); border-radius: 9px;
            display: inline-flex; font-size: 1.05rem; height: 34px; justify-content: center; width: 34px;
        }
        .dashboard-stat-label { color: var(--muted); font-size: .82rem; margin-top: 10px; }
        .dashboard-stat-value { color: var(--ink); font-size: 1.7rem; font-weight: 700; line-height: 1.1; margin-top: 2px; }

        /* Soft gradient KPI accents — used sparingly on the top stat row only */
        .dashboard-stat-card.grad { border: none; color: #ffffff; }
        .dashboard-stat-card.grad .dashboard-stat-icon { background: rgba(255,255,255,.2); }
        .dashboard-stat-card.grad .dashboard-stat-label { color: rgba(255,255,255,.85); }
        .dashboard-stat-card.grad .dashboard-stat-value { color: #ffffff; }
        .dashboard-stat-card.grad-1 { background: linear-gradient(135deg, #6366f1, #8b5cf6); box-shadow: 0 8px 20px -8px rgba(99,102,241,.55); }
        .dashboard-stat-card.grad-2 { background: linear-gradient(135deg, #2563eb, #38bdf8); box-shadow: 0 8px 20px -8px rgba(37,99,235,.5); }
        .dashboard-stat-card.grad-3 { background: linear-gradient(135deg, #059669, #34d399); box-shadow: 0 8px 20px -8px rgba(5,150,105,.5); }
        .dashboard-stat-card.grad-4 { background: linear-gradient(135deg, #d97706, #fb923c); box-shadow: 0 8px 20px -8px rgba(217,119,6,.5); }
        .dashboard-stat-card.grad:hover { transform: translateY(-2px); }

        .st-key-schema_card, .st-key-question_card,
        .st-key-sql_result_card, .st-key-preview_result_card,
        .st-key-text_result_card, .st-key-excel_result_card,
        .st-key-preview_card, .st-key-history_card, .st-key-recent_query_card {
            background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius);
            padding: 18px 20px; margin: 6px 0 14px; box-shadow: var(--shadow-sm);
            display: flex; flex-direction: column;
        }
        .st-key-schema_card h3, .st-key-question_card h3,
        .st-key-sql_result_card h3, .st-key-preview_result_card h3 { margin-bottom: 2px; font-size: 1.05rem; }

        .st-key-question_card textarea { min-height: 90px !important; }

        [data-testid="stTextArea"] textarea,
        [data-testid="stTextInput"] input,
        [data-baseweb="select"] > div,
        [data-testid="stFileUploaderDropzone"] {
            background: var(--surface-2) !important;
            border: 1px solid var(--line) !important;
            color: var(--ink) !important;
        }
        [data-testid="stCodeBlock"] pre { background: var(--surface-2) !important; border: 1px solid var(--line); border-radius: 10px; }

        .st-key-question_card div[data-testid="stPills"] button {
            background: var(--surface-2) !important; border: 1px solid var(--line) !important;
            border-radius: 999px !important; color: var(--primary-light) !important;
            font-size: .8rem !important; font-weight: 500 !important;
        }
        .st-key-question_card div[data-testid="stPills"] button:hover { border-color: var(--primary) !important; }
        .st-key-question_card div[data-testid="stPills"] button[aria-checked="true"] {
            background: var(--primary) !important;
            border-color: var(--primary) !important;
        }
        .st-key-question_card div[data-testid="stPills"] button[aria-checked="true"],
        .st-key-question_card div[data-testid="stPills"] button[aria-checked="true"] * { color: #ffffff !important; }

        button[kind="primary"] {
            background: var(--primary) !important;
            border: 1px solid var(--primary) !important;
            box-shadow: 0 4px 14px rgba(79, 70, 229, .28) !important;
        }
        button[kind="primary"], button[kind="primary"] * { color: #ffffff !important; }
        button[kind="primary"]:hover { background: var(--primary-dark) !important; }

        button[kind="secondary"] {
            background: var(--surface-2) !important;
            border: 1px solid var(--line) !important;
            color: var(--ink) !important;
        }
        button[kind="secondary"], button[kind="secondary"] * { color: var(--ink) !important; }
        button[kind="secondary"]:hover {
            border-color: var(--primary) !important;
            color: var(--primary-light) !important;
        }
        button[kind="secondary"]:hover, button[kind="secondary"]:hover * { color: var(--primary-light) !important; }

        .stApp:has([data-testid="stForm"]) [data-testid="stMainBlockContainer"] { max-width: 560px; padding-top: 8vh; }
        .stApp:has([data-testid="stForm"]) h1 { color: var(--ink); font-size: 1.9rem; text-align: center; }
        .stApp:has([data-testid="stForm"]) [data-testid="stForm"] { background: var(--surface-2); border: 1px solid var(--line); border-radius: var(--radius); padding: 28px 32px; }
        .stApp:has([data-testid="stForm"]) [data-testid="stFormSubmitButton"] button {
            background: var(--primary);
            border: 1px solid var(--primary);
            color: #ffffff; width: 100%;
        }
        .stApp:has([data-testid="stForm"]) [data-testid="stFormSubmitButton"] button:hover { background: var(--primary-dark); }

        @media (max-width: 900px) {
            [data-testid="stHorizontalBlock"] { flex-wrap: wrap; }
        }
        @media (max-width: 700px) {
            [data-testid="stMainBlockContainer"] { padding: 2.75rem 1rem 3rem; }
            .workspace-title { font-size: 1.3rem; }
        }

        /* Extra premium dashboard polish */
        .st-key-recent_query_card,
        .st-key-history_card {
            background: linear-gradient(145deg,#ffffff,#f8fafc) !important;
            border: 1px solid #e2e8f0 !important;
            border-radius: 18px !important;
            padding: 22px !important;
            box-shadow: 0 10px 30px rgba(15,23,42,0.06) !important;
            transition: .2s ease;
        }

        .st-key-recent_query_card:hover,
        .st-key-history_card:hover {
            transform: translateY(-3px);
            box-shadow: 0 16px 35px rgba(79,70,229,0.12) !important;
        }

        .workspace-title {
            font-size: 2rem !important;
            font-weight: 800 !important;
            letter-spacing: -0.03em;
        }

        .workspace-subtitle {
            font-size: .95rem !important;
        }

        .dashboard-stat-card {
            border-radius: 18px !important;
            min-height: 120px !important;
        }

        .sidebar-brand {
            font-size: 1.25rem !important;
            font-weight: 800 !important;
        }

        .sidebar-tip {
            margin-bottom: 18px !important;
        }


        .profile-card pre,
        .profile-card code {
            display:none !important;
        }

        .profile-card {
            overflow:hidden;
        }

</style>
        """,
        unsafe_allow_html=True,
    )


# ----------------------------------------------------------------------------
# Backend call wrappers
# ----------------------------------------------------------------------------

def get_answer(text2sql, data_info):
    try:
        return text2sql.get_answer(data_info)
    except ResourceExhausted:
        st.error(
            "The selected Gemini model has reached its API quota. "
            "Wait for the quota window to reset, use a different model, "
            "or check your Google AI Studio billing and rate limits."
        )
        return None
    except APIError as error:
        st.error(f"The OpenAI request failed: {error}")
        return None
    except Exception:
        logger.exception("SQL generation failed")
        st.error("Unable to generate SQL. Check the terminal for details.")
        return None


def get_explanation(text2sql, query):
    try:
        return text2sql.get_explanation(query)
    except ResourceExhausted:
        st.error("The selected Gemini model has reached its API quota while generating the explanation.")
    except APIError as error:
        st.error(f"The model explanation request failed: {error}")
    except Exception:
        logger.exception("SQL explanation failed")
        st.error("Unable to generate the SQL explanation. Check the terminal for details.")

    return None


def transcribe_voice(audio_file):
    """Convert a Streamlit microphone recording into a text question."""
    if audio_file is None:
        return ""

    audio_bytes = audio_file.getvalue()
    if not audio_bytes:
        return ""

    # Avoid sending the same recording to the API on every Streamlit rerun.
    audio_hash = hashlib.sha256(audio_bytes).hexdigest()
    if st.session_state.get("voice_audio_hash") == audio_hash:
        return st.session_state.get("voice_transcript", "")

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        st.error(
            "OPENAI_API_KEY is not configured. Add your OpenAI API key to "
            "the project's environment/.env file and restart Streamlit."
        )
        return ""

    try:
        client = OpenAI(api_key=api_key)

        with st.spinner("🎤 Converting your voice to text..."):
            transcription = client.audio.transcriptions.create(
                model="gpt-4o-mini-transcribe",
                file=("voice.wav", audio_bytes, "audio/wav"),
            )

        transcript = (transcription.text or "").strip()

        st.session_state["voice_audio_hash"] = audio_hash
        st.session_state["voice_transcript"] = transcript

        return transcript

    except APIError as error:
        st.error(f"Voice transcription failed: {error}")
        return ""
    except Exception:
        logger.exception("Voice transcription failed")
        st.error("Unable to convert the voice recording to text. Check the terminal.")
        return ""


def add_query_history(question, query):
    email = st.session_state["user_email"]
    history = save_user_query_history(email, question, query)
    st.session_state["query_history"] = history


def render_query_history():
    email = st.session_state["user_email"]
    history = get_query_history(email)
    st.session_state["query_history"] = history

    st.subheader("Query History")
    search_text = st.text_input("Search Query History", key="query_history_search")
    if st.button("Clear Query History", key="clear_query_history"):
        clear_query_history(email)
        st.session_state["query_history"] = []
        st.rerun()

    if not history:
        return

    search_text = search_text.strip().lower()
    filtered_history = [
        history_item
        for history_item in history
        if search_text in history_item["question"].lower()
        or search_text in history_item["query"].lower()
    ]

    if not filtered_history:
        st.info("No matching queries found.")
        return

    for index, history_item in enumerate(reversed(filtered_history)):
        with st.container(border=True, key=f"history_card_{index}"):
            st.markdown(f"**Question:** {history_item['question']}")
            st.markdown("**SQL**")
            st.code(history_item["query"], language="sql")
            if st.button("Use this question again", key=f"rerun_history_{index}"):
                st.session_state["ask_question"] = history_item["question"]
                st.session_state["pending_section"] = "Text2SQL"
                st.rerun()


STAT_GRADIENTS = ["grad-1", "grad-2", "grad-3", "grad-4"]


def stat_card_html(icon, label, value, gradient_class):
    return f"""
    <div class="dashboard-stat-card grad {gradient_class}">
        <div class="dashboard-stat-icon">{icon}</div>
        <div class="dashboard-stat-label">{label}</div>
        <div class="dashboard-stat-value">{value}</div>
    </div>
    """


def render_dashboard():
    history = get_query_history(st.session_state["user_email"])
    st.title("Dashboard")
    st.caption("Overview of your Text2SQL activity")

    if not history:
        st.info("No queries yet. Generate your first SQL query to see statistics here.")
        return

    total_queries = len(history)
    queries_with_results = sum(item.get("has_results", False) for item in history)
    history_items = len(history)

    total_column, results_column, history_column = st.columns(3, gap="medium")
    total_column.markdown(
        stat_card_html("📊", "Total Queries", total_queries, "grad-1"),
        unsafe_allow_html=True,
    )
    results_column.markdown(
        stat_card_html("✅", "Queries with Results", queries_with_results, "grad-3"),
        unsafe_allow_html=True,
    )
    history_column.markdown(
        stat_card_html("🗂️", "Query History Items", history_items, "grad-2"),
        unsafe_allow_html=True,
    )

    st.subheader("Recent Queries")
    st.caption("Your latest SQL queries")
    for index, history_item in enumerate(reversed(history[-5:])):
        with st.container(border=True, key=f"recent_query_card_{index}"):
            st.markdown(f"**Question**  \n{history_item['question']}")
            st.markdown("**SQL**")
            st.code(history_item["query"], language="sql")


# ----------------------------------------------------------------------------
# App entry point
# ----------------------------------------------------------------------------

st.set_page_config(page_title="Text2SQL-AI", page_icon="app/images/icon.png")

inject_logged_in_styles()
initialize_auth_state()
if not st.session_state["authenticated"]:
    render_auth_page()
    st.stop()

init_session_state()

if "model_prefill_done" not in st.session_state:
    saved_type, saved_name = get_saved_model(st.session_state["user_email"])
    if saved_type:
        st.session_state["model_type"] = saved_type
        st.session_state["model_name"] = saved_name
    st.session_state["model_prefill_done"] = True

if "pending_section" in st.session_state:
    st.session_state["app_section"] = st.session_state.pop("pending_section")

with st.sidebar:
    st.markdown(
        """
        <div class="sidebar-brand">
            <span class="sidebar-brand-icon">▤</span>
            Text2SQL-AI
        </div>
        """,
        unsafe_allow_html=True
    )

    st.markdown("<div class='sidebar-section-label'>WORKSPACE</div>", unsafe_allow_html=True)

    section = st.radio(
        "Section",
        ["Dashboard", "Text2SQL", "Query History"],
        key="app_section",
        label_visibility="collapsed"
    )

    st.divider()
    st.markdown("<div class='sidebar-section-label'>MODEL</div>", unsafe_allow_html=True)
    model_info = sidebar_block()
    st.markdown(
        """
        <div class="sidebar-tip">
            <div class="sidebar-tip-title">💡 Tip</div>
            <div class="sidebar-tip-body">Describe your table columns clearly for more accurate SQL — e.g. "orders(id, customer, total, date)".</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
# User profile sidebar is rendered by auth.py only.
render_user_sidebar()


if section == "Dashboard":
    render_dashboard()
    st.stop()
if section == "Query History":
    render_query_history()
    st.stop()

# ---------------------------------------------------------------------------
# Text2SQL workspace
# ---------------------------------------------------------------------------

history = get_query_history(st.session_state["user_email"])
total_queries = len(history)
queries_with_results = sum(item.get("has_results", False) for item in history)

st.session_state.setdefault("data_source", "Upload File")
st.session_state.setdefault("ask_question", "")
st.session_state.setdefault("stat_tables", None)
st.session_state.setdefault("stat_columns", None)

st.markdown(
    f"""
    <div class="workspace-header">
        <div>
            <div class="workspace-title">Welcome back, {st.session_state['user_name']} 👋</div>
            <div class="workspace-subtitle">Convert natural language into SQL queries from your data.</div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

stat_col1, stat_col2, stat_col3, stat_col4 = st.columns(4, gap="medium")
tables_value = st.session_state["stat_tables"] if st.session_state["stat_tables"] is not None else "-"
columns_value = st.session_state["stat_columns"] if st.session_state["stat_columns"] is not None else "-"

stat_col1.markdown(stat_card_html("📊", "Tables", tables_value, "grad-1"), unsafe_allow_html=True)
stat_col2.markdown(stat_card_html("🧱", "Columns", columns_value, "grad-4"), unsafe_allow_html=True)
stat_col3.markdown(stat_card_html("📝", "Queries Generated", total_queries, "grad-2"), unsafe_allow_html=True)
stat_col4.markdown(stat_card_html("✅", "Queries with Results", queries_with_results, "grad-3"), unsafe_allow_html=True)

st.html("<br>")

left_col, right_col = st.columns([1, 1], gap="large")

files = None
data_info = ""

with left_col:
    with st.container(border=True, key="schema_card"):
        st.subheader("Database Schema / Upload Data")
        st.caption("Upload a CSV/XLSX file or describe your table structure.")
        data_source = st.radio(
            "Data source",
            ["Upload File", "Text Input"],
            key="data_source",
            horizontal=True,
            label_visibility="collapsed",
        )

        if data_source == "Upload File":
            files = st.file_uploader(
                "Upload CSV/XLSX", type=["csv", "xlsx"], accept_multiple_files=True, key="excel_tab_files"
            )
            if files:
                tables, columns = parse_uploaded_files_counts(files)
                if tables:
                    st.session_state["stat_tables"] = tables
                if columns:
                    st.session_state["stat_columns"] = columns
            st.button("Try Demo", key="excel_try_demo_button", on_click=fill_excel_demo)
        else:
            data_info = st.text_area(
                "Describe Your Data",
                placeholder="Example: employees(id, name, department, salary)",
                key="data_info_text",
            )
            if data_info:
                tables, columns = parse_text_schema_counts(data_info)
                if tables:
                    st.session_state["stat_tables"] = tables
                if columns:
                    st.session_state["stat_columns"] = columns
            st.button("Try Demo", key="try_sample_button", on_click=fill_text_sample)

with right_col:
    with st.container(border=True, key="question_card"):
        st.subheader("Ask Your Question")
        st.caption("Write a question in natural language, or pick an example below.")

        # Voice input: record a natural-language question with the microphone.
        voice_audio = st.audio_input(
            "🎤 Speak your question",
            sample_rate=16000,
            key="voice_query_audio",
            help="Example: Show all employees from the IT department.",
        )

        if voice_audio is not None:
            voice_text = transcribe_voice(voice_audio)
            if voice_text:
                st.session_state["ask_question"] = voice_text
                st.success("Voice converted to text.")

        question_text = st.text_area(
            "Write your question",
            key="ask_question",
            placeholder="Write a question in natural language about your data.",
            label_visibility="collapsed",
        )
        st.caption(f"{len(question_text)}/500")

        st.pills(
            "Quick questions",
            EXAMPLE_QUESTIONS,
            key="quick_pills",
            label_visibility="collapsed",
            on_change=apply_pill_selection,
        )

        generate_col, demo_col = st.columns([1, 1])
        with generate_col:
            ask_button = st.button("Generate SQL", key="generate_button", type="primary")

# ---------------------------------------------------------------------------
# Handle "Generate SQL"
# ---------------------------------------------------------------------------

result_query = None
result_text2sql = None
result_is_demo = False
result_source = data_source

if ask_button:
    question_text = st.session_state["ask_question"]

    if data_source == "Text Input":
        current_data_info = st.session_state.get("data_info_text", "")
        st.session_state["text_tab_info"] = current_data_info
        st.session_state["text_tab_question"] = question_text

        demo_query = get_demo_sql(current_data_info, question_text)
        is_demo_result = demo_query is not None

        if not is_demo_result and (message := widget_control("control_type")):
            st.error(message)
        else:
            if is_demo_result:
                result_query = demo_query
                result_is_demo = True
            else:
                result_text2sql = Text2SQL(model_info, question_text)
                with st.spinner("Generating SQL..."):
                    result_query = get_answer(result_text2sql, current_data_info)

            if result_query is not None and not result_is_demo and "don't" not in result_query:
                add_query_history(question_text, result_query)

    else:  # Upload File
        current_files = st.session_state.get("excel_tab_files")
        st.session_state["excel_tab_question"] = question_text

        is_excel_demo = (
            st.session_state.get("excel_demo_mode", False)
            and question_text.strip() in DEMO_QA
            and not current_files
        )

        if (message := widget_control("excel_tab_control")) and not is_excel_demo:
            st.error(message)
        else:
            if is_excel_demo:
                result_text2sql = build_excel_demo_text2sql()
                result_query = DEMO_QA[question_text.strip()]
                result_is_demo = True
                refresh_stats_from_engine(result_text2sql.engine)
            else:
                result_text2sql = Text2SQL(model_info, question_text)
                try:
                    with st.spinner("Loading data and generating SQL..."):
                        result_query = result_text2sql.init_db(current_files)
                    refresh_stats_from_engine(result_text2sql.engine)
                except ResourceExhausted:
                    st.error(
                        "The selected Gemini model has reached its API quota. "
                        "Wait for the quota window to reset, use a different model, "
                        "or check your Google AI Studio billing and rate limits."
                    )
                except APIError as error:
                    st.error(f"The OpenAI request failed: {error}")
                except (OSError, ValueError, ImportError):
                    logger.exception("Uploaded file could not be processed")
                    st.error("Unable to read the uploaded file. Check that it is a valid CSV or XLSX file.")
                except Exception:
                    logger.exception("Excel/CSV query generation failed")
                    st.error("Unable to process the uploaded file. Check the terminal for details.")

            if result_query is not None and not result_is_demo and "don't" not in result_query:
                add_query_history(question_text, result_query)

# ---------------------------------------------------------------------------
# Results: Generated SQL + Query Results, side by side
# ---------------------------------------------------------------------------

if result_query:
    st.html("<br>")

    if "don't" in result_query:
        st.markdown(result_query)
    else:
        sql_col, preview_col = st.columns(2, gap="large")

        with sql_col:
            with st.container(border=True, key="sql_result_card"):
                st.subheader("Generated SQL")
                st.caption("SQL query generated from your question.")
                st.code(result_query, language="sql")
                if result_is_demo:
                    st.caption("Demo Result — generated locally")
                elif result_text2sql is not None:
                    explanation = get_explanation(result_text2sql, result_query)
                    if explanation:
                        st.subheader("SQL Explanation")
                        st.write(explanation)

        with preview_col:
            with st.container(border=True, key="preview_result_card"):
                st.subheader("Query Results")
                st.caption("Result returned from your database.")

                can_preview = result_source == "Upload File" and result_text2sql is not None
                if not can_preview:
                    st.info("Preview is available for data uploaded as CSV/XLSX.")
                elif not result_query.strip().lower().startswith("select"):
                    st.warning("Only SELECT queries are executed for preview.")
                else:
                    try:
                        try:
                            result_df = result_text2sql.run_query(result_query)
                        except ValueError:
                            raise
                        except Exception as db_error:
                            if result_is_demo:
                                raise
                            data_info_for_fix = getattr(result_text2sql, "table_info", "") or ""
                            with st.spinner("First attempt failed — asking the AI to fix the SQL..."):
                                fixed_query = result_text2sql.fix_query(
                                    data_info_for_fix, result_query, db_error
                                )
                            st.info("The generated SQL had an error, so it was corrected automatically:")
                            st.code(fixed_query, language="sql")
                            result_query = fixed_query
                            result_df = result_text2sql.run_query(fixed_query)

                        if not result_df.empty and not result_is_demo:
                            mark_query_has_results(st.session_state["user_email"], result_query)
                        st.dataframe(result_df, use_container_width=True)
                        st.download_button(
                            "Download Results as CSV",
                            result_df.to_csv(index=False).encode("utf-8"),
                            "query_results.csv",
                            "text/csv",
                        )

                        numeric_cols = list(result_df.select_dtypes(include="number").columns)
                        text_cols = list(result_df.select_dtypes(exclude="number").columns)
                        chartable_numeric_cols = [
                            col for col in numeric_cols
                            if col.lower() != "id" and not col.lower().endswith("_id")
                        ] or numeric_cols
                        if chartable_numeric_cols and text_cols and len(result_df) <= 30:
                            import plotly.graph_objects as go

                            chart_df = result_df.sort_values(
                                by=chartable_numeric_cols[0], ascending=False
                            )

                            fig = go.Figure(
                                go.Bar(
                                    x=chart_df[text_cols[0]],
                                    y=chart_df[chartable_numeric_cols[0]],
                                    marker=dict(
                                        color=chart_df[chartable_numeric_cols[0]],
                                        colorscale=[[0, "#818cf8"], [1, "#4f46e5"]],
                                        line=dict(width=0),
                                    ),
                                    marker_cornerradius=8,
                                    text=chart_df[chartable_numeric_cols[0]],
                                    texttemplate="%{text:,.0f}",
                                    textposition="outside",
                                    textfont=dict(color="#475569", size=12),
                                    hovertemplate="<b>%{x}</b><br>"
                                    + chartable_numeric_cols[0]
                                    + ": %{y:,.0f}<extra></extra>",
                                )
                            )
                            fig.update_layout(
                                height=340,
                                margin=dict(l=10, r=10, t=30, b=10),
                                plot_bgcolor="rgba(0,0,0,0)",
                                paper_bgcolor="rgba(0,0,0,0)",
                                font=dict(family="Inter, Segoe UI, sans-serif", color="#1f2430"),
                                xaxis=dict(
                                    showgrid=False,
                                    linecolor="#e6e9f0",
                                    tickfont=dict(color="#6b7280", size=12),
                                ),
                                yaxis=dict(
                                    showgrid=True,
                                    gridcolor="#f1f3f8",
                                    zeroline=False,
                                    tickfont=dict(color="#6b7280", size=12),
                                    title=dict(
                                        text=chartable_numeric_cols[0].title(),
                                        font=dict(color="#6b7280", size=12),
                                    ),
                                ),
                                bargap=0.35,
                                showlegend=False,
                            )
                            st.plotly_chart(fig, use_container_width=True)
                    except ValueError as error:
                        logger.exception("Read-only SQL validation failed")
                        st.error(str(error))
                    except Exception:
                        logger.exception("SQL preview failed")
                        st.error(
                            "Unable to execute the SQL query, even after an automatic fix attempt. "
                            "Check that the generated SQL is valid."
                        )
