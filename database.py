import sqlite3
import pandas as pd

DATABASE = "sample_database.db"

def execute_query(sql):
    conn = sqlite3.connect(DATABASE)
    df = pd.read_sql_query(sql, conn)
    conn.close()
    return df
