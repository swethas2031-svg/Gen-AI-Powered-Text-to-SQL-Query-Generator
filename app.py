import streamlit as st
from sql_generator import generate_sql
from database import execute_query

st.set_page_config(page_title="Gen AI Text-to-SQL Generator")

st.title("Gen AI Powered Text-to-SQL Query Generator")

question = st.text_area("Enter your question")

if st.button("Generate SQL"):
    sql = generate_sql(question)

    st.subheader("Generated SQL")
    st.code(sql, language="sql")

    try:
        result = execute_query(sql)
        st.subheader("Query Result")
        st.dataframe(result)
    except Exception as e:
        st.error(e)
