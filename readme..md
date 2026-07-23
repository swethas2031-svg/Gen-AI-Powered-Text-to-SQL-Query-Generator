# Gen AI Powered Text-to-SQL Query Generator

## Overview

The Gen AI Powered Text-to-SQL Query Generator is an AI-based application that converts natural language questions into SQL queries. Users can enter queries in plain English, and the system automatically generates SQL statements, executes them on a database, and displays the results.

## Features

- Convert natural language into SQL queries
- AI-powered SQL generation
- Execute SQL queries automatically
- Display query results in tabular format
- Supports SQLite, MySQL, PostgreSQL, and SQL Server
- User-friendly interface using Streamlit
- Error handling and SQL validation
- Export query results to CSV

## Technologies Used

- Python
- Streamlit
- Google Gemini API / OpenAI API
- SQLAlchemy
- SQLite
- Pandas

## Project Structure

```
Gen-AI-Powered-Text-to-SQL-Query-Generator/
│── app.py
│── main.py
│── database.py
│── llm.py
│── prompt.py
│── sql_generator.py
│── validator.py
│── utils.py
│── requirements.txt
│── README.md
│── LICENSE
│── .gitignore
│── screenshots/
│── sample_database.db
```

## Workflow

1. User enters a question in natural language.
2. The AI model processes the question.
3. SQL query is generated automatically.
4. The generated SQL is validated.
5. The SQL query is executed on the selected database.
6. Results are displayed in a table.
7. Users can export the results.

## Example

**User Input**

```
Show all employees whose salary is greater than 50000.
```

**Generated SQL**

```sql
SELECT * FROM Employees
WHERE Salary > 50000;
```

## Future Enhancements

- Voice-based query input
- Multi-database support
- Dashboard visualizations
- AI-powered SQL optimization
- User authentication
- Query history

## Installation

```bash
pip install -r requirements.txt
```

## Run the Project

```bash
streamlit run app.py
```

## Author

**Swetha S**



## License

This project is licensed under the MIT License.
