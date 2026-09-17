import os

from dotenv import load_dotenv
from langgraph.checkpoint.mysql.pymysql import PyMySQLSaver


load_dotenv()


def get_checkpointer():
    host = os.getenv("MYSQL_HOST", "127.0.0.1")
    port = os.getenv("MYSQL_PORT", "3306")
    database = os.getenv("MYSQL_DATABASE", "vehicle_agent")
    username = os.getenv("MYSQL_USERNAME", "root")
    password = os.getenv("MYSQL_PASSWORD", "")

    db_uri = (
        f"mysql://{username}:{password}"
        f"@{host}:{port}/{database}"
    )

    return PyMySQLSaver.from_conn_string(db_uri)