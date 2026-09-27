import hashlib
import hmac
import json
import secrets
from pathlib import Path

import streamlit as st


USERS_FILE = Path(__file__).resolve().parent.parent / "users.json"
PBKDF2_ITERATIONS = 200_000


def _load_users():
    if not USERS_FILE.exists():
        return {}

    try:
        with USERS_FILE.open("r", encoding="utf-8") as file:
            users = json.load(file)
        return users if isinstance(users, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_users(users):
    temporary_file = USERS_FILE.with_suffix(".tmp")
    with temporary_file.open("w", encoding="utf-8") as file:
        json.dump(users, file, indent=2)
    temporary_file.replace(USERS_FILE)


def get_query_history(email):
    user = _load_users().get(email.strip().lower(), {})
    history = user.get("query_history", [])
    return history if isinstance(history, list) else []


def add_query_history(email, question, query):
    users = _load_users()
    user = users.get(email.strip().lower())
    if not user:
        return []

    history = user.setdefault("query_history", [])
    history.append({"question": question, "query": query, "has_results": False})
    _save_users(users)
    return history


def mark_query_has_results(email, query):
    users = _load_users()
    user = users.get(email.strip().lower())
    if not user:
        return

    for history_item in reversed(user.get("query_history", [])):
        if history_item.get("query") == query:
            history_item["has_results"] = True
            _save_users(users)
            return


def clear_query_history(email):
    users = _load_users()
    user = users.get(email.strip().lower())
    if user:
        user["query_history"] = []
        _save_users(users)


def get_saved_model(email):
    """Feature: remember the user's last-used model choice (not the API key —
    that is never saved to disk)."""
    user = _load_users().get(email.strip().lower(), {})
    return user.get("model_type"), user.get("model_name")


def save_model_choice(email, model_type, model_name):
    users = _load_users()
    user = users.get(email.strip().lower())
    if not user:
        return
    user["model_type"] = model_type
    user["model_name"] = model_name
    _save_users(users)


def _hash_password(password, salt):
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PBKDF2_ITERATIONS,
    ).hex()


def initialize_auth_state():
    defaults = {
        "authenticated": False,
        "user_name": "",
        "user_email": "",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def register_user(name, email, password, confirm_password):
    name = name.strip()
    email = email.strip().lower()

    if not all((name, email, password, confirm_password)):
        return False, "All fields are required."
    if password != confirm_password:
        return False, "Password and confirm password must match."
    if len(password) < 6:
        return False, "Password must be at least 6 characters long."
    if "@" not in email or "." not in email.rsplit("@", 1)[-1]:
        return False, "Enter a valid email address."

    users = _load_users()
    if email in users:
        return False, "An account with this email already exists."

    salt = secrets.token_hex(16)
    users[email] = {
        "name": name,
        "salt": salt,
        "password_hash": _hash_password(password, salt),
    }
    _save_users(users)
    return True, "Registration successful. You can now log in."


def login_user(email, password):
    email = email.strip().lower()
    user = _load_users().get(email)

    if not user or not password:
        return False

    password_hash = _hash_password(password, user["salt"])
    if not hmac.compare_digest(password_hash, user["password_hash"]):
        return False

    st.session_state["authenticated"] = True
    st.session_state["user_name"] = user["name"]
    st.session_state["user_email"] = email
    return True


def logout_user():
    st.session_state["authenticated"] = False
    st.session_state["user_name"] = ""
    st.session_state["user_email"] = ""


def render_auth_page():
    st.markdown(
        """
        <style>
        :root {
            --primary: #4f46e5;
            --primary-dark: #4338ca;
            --canvas: #f4f6fb;
            --surface: #ffffff;
            --surface-2: #fafbfd;
            --ink: #1f2430;
            --muted: #6b7280;
            --line: #e6e9f0;
            --radius: 14px;
        }
        html, body, .stApp {
            background: linear-gradient(135deg,#eef4ff,#ffffff) !important;
        }
        section[data-testid="stSidebar"] { display: none !important; }
        div[data-testid="stSidebarCollapsedControl"] { display: none !important; }
        .stApp:has([data-testid="stForm"]) [data-testid="stMainBlockContainer"] {
            max-width: 620px;
            padding-top: 6vh;
        }

        /* Outer card: the ONLY box. Everything inside sits directly on it. */
        .st-key-auth_card {
            background: var(--surface);
            border: 1px solid var(--line);
            border-radius: var(--radius);
            box-shadow: 0 20px 45px rgba(79,70,229,.12);
            margin: 0 auto;
            max-width: 560px;
            padding: 36px 48px 32px;
        }

        /* Tighten the default Streamlit block spacing so sections read as
           one cohesive form instead of loosely stacked widgets. */
        .st-key-auth_card [data-testid="stVerticalBlock"] {
            gap: 0.55rem;
        }

        .st-key-auth_card .auth-brand {
            background: linear-gradient(90deg,#2563eb,#4f46e5);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-size: 2.1rem;
            font-weight: 700;
            text-align: center;
            letter-spacing: -.01em;
            line-height: 1.2;
        }
        .st-key-auth_card .auth-subtitle {
            color: var(--muted);
            font-size: 0.95rem;
            margin: 4px 0 18px;
            text-align: center;
        }

        /* Login / Register toggle */
        .st-key-auth_card [data-testid="stRadio"] > label { display: none; }
        .st-key-auth_card [data-testid="stRadio"] { margin-bottom: 20px; }
        .st-key-auth_card [role="radiogroup"] {
            background: var(--surface-2);
            border: 1px solid var(--line);
            border-radius: 10px;
            display: flex;
            gap: 4px;
            padding: 4px;
        }
        .st-key-auth_card [role="radio"] {
            background: transparent;
            border-radius: 7px;
            flex: 1;
            justify-content: center;
            padding: 7px 10px;
            transition: background .15s ease;
        }
        .st-key-auth_card [role="radio"] p {
            color: var(--muted);
            font-size: 0.92rem;
            font-weight: 500;
        }
        .st-key-auth_card [role="radio"][aria-checked="true"] {
            background: linear-gradient(90deg,#2563eb,#4f46e5);
            box-shadow: 0 4px 10px rgba(79,70,229,.25);
        }
        .st-key-auth_card [role="radio"][aria-checked="true"] p {
            color: #ffffff;
            font-weight: 600;
        }

        /* Section heading */
        .st-key-auth_card h3 {
            color: var(--ink);
            font-size: 1.25rem;
            margin: 4px 0 2px;
        }
        .st-key-auth_card [data-testid="stCaptionContainer"] {
            color: var(--muted);
            font-size: 0.88rem;
            margin-bottom: 0;
        }

        /* Form: no extra card, no extra background — just spacing */
        .st-key-auth_card [data-testid="stForm"] {
            background: transparent !important;
            border: none !important;
            border-radius: 0 !important;
            box-shadow: none !important;
            margin-top: 6px;
            padding: 0 !important;
        }

        /* Field labels */
        .st-key-auth_card [data-testid="stTextInput"] label p {
            color: #475569;
            font-size: 0.85rem;
            font-weight: 600;
            margin-bottom: 2px;
            text-transform: uppercase;
            letter-spacing: .02em;
        }
        .st-key-auth_card [data-testid="stTextInput"] {
            margin-bottom: 14px;
        }

        /* Input boxes */
        .st-key-auth_card [data-testid="stTextInput"] input {
            background: var(--surface-2);
            border: 1px solid #dbe3f0;
            border-radius: 10px;
            color: #1e293b;
            height: 46px;
            padding-left: 14px;
        }
        .st-key-auth_card [data-testid="stTextInput"] input:focus {
            background: #ffffff;
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(79,70,229,0.15);
        }
        .st-key-auth_card [data-testid="stTextInput"] button svg { fill: var(--muted); }

        /* Submit button */
        .st-key-auth_card [data-testid="stFormSubmitButton"] { margin-top: 8px; }
        .st-key-auth_card [data-testid="stFormSubmitButton"] button {
            background: linear-gradient(90deg,#2563eb,#4f46e5);
            border: none;
            border-radius: 10px;
            height: 46px;
            font-size: 1rem;
            font-weight: 600;
            width: 100%;
            transition: filter .15s ease, box-shadow .15s ease;
        }
        .st-key-auth_card [data-testid="stFormSubmitButton"] button,
        .st-key-auth_card [data-testid="stFormSubmitButton"] button * {
            color: #ffffff !important;
        }
        .st-key-auth_card [data-testid="stFormSubmitButton"] button:hover {
            filter: brightness(1.06);
            box-shadow: 0 8px 20px rgba(79,70,229,.28);
        }

        @media (max-width: 480px) {
            .stApp:has([data-testid="stForm"]) [data-testid="stMainBlockContainer"] { padding-top: 3vh; }
            .st-key-auth_card { padding: 24px 20px 22px; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    with st.container(border=True, key="auth_card"):
        st.markdown("<div class='auth-brand'>Text2SQL-AI</div>", unsafe_allow_html=True)
        st.markdown("<div class='auth-subtitle'>Natural language &rarr; SQL</div>", unsafe_allow_html=True)
        page = st.radio("Account", ["Login", "Register"], horizontal=True, label_visibility="collapsed")

        if page == "Register":
            st.subheader("Create an account")
            st.caption("It only takes a minute.")
            with st.form("register_form"):
                name = st.text_input("Name")
                email = st.text_input("Email")
                password = st.text_input("Password", type="password")
                confirm_password = st.text_input("Confirm Password", type="password")
                submitted = st.form_submit_button("Register", type="primary", use_container_width=True)

            if submitted:
                registered, message = register_user(name, email, password, confirm_password)
                if registered:
                    st.success(message)
                else:
                    st.error(message)
        else:
            st.subheader("Welcome back")
            st.caption("Sign in to continue to your workspace.")
            with st.form("login_form"):
                email = st.text_input("Email")
                password = st.text_input("Password", type="password")
                submitted = st.form_submit_button("Login", type="primary", use_container_width=True)

            if submitted:
                if login_user(email, password):
                    st.rerun()
                st.error("Incorrect email or password.")


def render_user_sidebar():
    with st.sidebar:
        name = st.session_state.get("user_name", "User")
        email = st.session_state.get("user_email", "")
        initial = name[0].upper() if name else "U"

        st.markdown(
            f"""
            <style>
            .user-profile-card {{
                margin-top: 18px;
                padding: 14px 16px;
                background: linear-gradient(145deg,#ffffff,#f8fafc);
                border: 1px solid #e2e8f0;
                border-radius: 16px;
                box-shadow: 0 10px 25px rgba(15,23,42,0.08);
                display: flex;
                align-items: center;
                gap: 12px;
                transition: box-shadow .2s ease, transform .2s ease;
            }}
            .user-profile-card:hover {{
                box-shadow: 0 14px 32px rgba(79,70,229,0.14);
                transform: translateY(-2px);
            }}
            .user-profile-avatar {{
                flex-shrink: 0;
                width: 46px;
                height: 46px;
                border-radius: 50%;
                background: linear-gradient(135deg,#2563eb,#7c3aed);
                color: #ffffff;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 19px;
                font-weight: 800;
                box-shadow: 0 4px 10px rgba(79,70,229,.35);
            }}
            .user-profile-info {{
                overflow: hidden;
                min-width: 0;
            }}
            .user-profile-name {{
                font-size: 14px;
                font-weight: 700;
                color: #111827;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }}
            .user-profile-email {{
                margin-top: 2px;
                font-size: 11.5px;
                color: #64748b;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }}
            div[data-testid="stSidebar"] div[data-testid="stButton"] button {{
                margin-top: 12px;
                border: 1px solid #fecaca !important;
                background: #fff5f5 !important;
                color: #dc2626 !important;
                font-weight: 600 !important;
                border-radius: 10px !important;
                transition: background .15s ease, border-color .15s ease;
            }}
            div[data-testid="stSidebar"] div[data-testid="stButton"] button:hover {{
                background: #fee2e2 !important;
                border-color: #fca5a5 !important;
                color: #b91c1c !important;
            }}
            </style>

            <div class="user-profile-card">
                <div class="user-profile-avatar">{initial}</div>
                <div class="user-profile-info">
                    <div class="user-profile-name">{name}</div>
                    <div class="user-profile-email">{email}</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if st.button("🚪 Logout", key="logout_button", use_container_width=True):
            logout_user()
            st.rerun()
