import streamlit as st


def init_session_state():
    defaults = {"model_type": "GPT", "model_name": "gpt-4o", "api_key": "", "text_tab_info": "", "text_tab_question": "", "excel_tab_files": "", "excel_tab_question": "", "query_history": []}

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def widget_control(control_type="control_type"):
    if not (st.session_state["model_name"] and st.session_state["api_key"]):
        return "Select a Model and / or Write Your API Key"

    if control_type == "control_type":
        if not (st.session_state["text_tab_info"] and st.session_state["text_tab_question"]):
            return "Describe Your Data and/or Write Your Question"

    if control_type == "excel_tab_control":
        if not (st.session_state["excel_tab_files"] and st.session_state["excel_tab_question"]):
            return "Upload Your Excel(s) and/or Write Your Question"
