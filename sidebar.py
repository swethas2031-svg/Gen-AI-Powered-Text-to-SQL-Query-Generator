import streamlit as st

from auth import save_model_choice


def sidebar_block():
    model_dict = {
        "GPT": ["gpt-4o", "gpt-4-turbo", "gpt-4", "gpt-3.5-turbo", "Other"],
        "Gemini": ["gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash", "Other"]
    }

    with st.popover("Model Settings"):
        st.markdown(
            "<div style='font-weight:700; font-size:1rem; color:#eceef3; margin-bottom:6px;'>⚙️ Model Settings</div>"
            "<div style='font-size:.78rem; color:#9298ab; margin-bottom:10px;'>Choose a model and enter your API key.</div>",
            unsafe_allow_html=True,
        )
        model_type = st.radio("Model", options=["GPT", "Gemini"], key="model_type")

        if model_type:
            model_options = model_dict[model_type]
            if st.session_state.get("model_name") not in model_options:
                st.session_state["model_name"] = model_options[0]

            model_name = st.selectbox(f"Select {model_type} Model :robot_face:", options=model_options, key="model_name")
            other_model = st.empty()

            if model_name == "Other":
                other_model = st.empty()
                other_model = other_model.text_input(f"Write {model_type} Model", key="other_model")
                model_name = other_model
                del other_model
            else:
                other_model.empty()

            api_key = st.text_input("API Key :key:", type="password", key="api_key")

    st.caption(f"{model_type} · {model_name}")

    if api_key:
        st.caption("API key configured")

    model_info = {"model_type": model_type, "model_name": model_name, "api_key": api_key}

    # Feature: remember the user's last-used model (never the API key itself)
    # so they don't have to re-pick it on every login.
    if api_key and st.session_state.get("user_email"):
        save_model_choice(st.session_state["user_email"], model_type, model_name)

    return model_info
