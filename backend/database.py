# ============================================================
#  database.py — Database Connection, Schema Extraction, Query Execution
#
#  Supports:
#    • MySQL        (via mysql-connector-python)
#    • MSSQL        (via pyodbc — requires ODBC Driver 17 for SQL Server)
#
#  How it works:
#    1. test_connection()  → checks credentials are correct
#    2. get_schema()       → reads all tables + columns from the DB
#    3. execute_query()    → runs a SQL string and returns rows
# ============================================================

import mysql.connector          # pip install mysql-connector-python
import pyodbc                   # pip install pyodbc
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


# ============================================================
#  HELPER: Build a database connection
#  Called internally — not exposed as an API endpoint
# ============================================================

def get_connection(config):
    """
    Create and return a live database connection.
    config = ConnectionConfig object from main.py

    MySQL  → uses mysql.connector
    MSSQL  → uses pyodbc with ODBC Driver 17
    """

    if config.db_type.lower() == "mysql":
        # ── MySQL Connection ─────────────────────────────────
        conn = mysql.connector.connect(
            host=config.host,
            port=config.port or 3306,       # default MySQL port
            user=config.username,
            password=config.password,
            database=config.database,
            connection_timeout=10           # fail fast if host unreachable
        )
        return conn

    elif config.db_type.lower() == "mssql":
        # ── Microsoft SQL Server Connection ──────────────────
        # Requires: ODBC Driver 17 for SQL Server installed on your machine
        # Download: https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server
        """
        connection_string = (
            f"DRIVER={{ODBC Driver 17 for SQL Server}};"
            #f"SERVER={config.host},{config.port or 1433};"  # default MSSQL port = 1433
            f"SERVER={config.host};"
            f"DATABASE={config.database};"
            f"UID={config.username};"
            f"PWD={config.password};"
            f"Connection Timeout=10;"
        )
        """
        connection_string = (
            f"DRIVER={{ODBC Driver 17 for SQL Server}};"
            f"SERVER={config.host};"          # no port for SQLEXPRESS
            f"DATABASE={config.database};"
            f"UID={config.username};"
            f"PWD={config.password};"
            f"TrustServerCertificate=yes;"
            f"Connection Timeout=30;"
        )
        conn = pyodbc.connect(connection_string)
        return conn

    else:
        raise ValueError(f"Unsupported database type: '{config.db_type}'. Use 'mysql' or 'mssql'.")


# ============================================================
#  1. TEST CONNECTION
# ============================================================

def test_connection(config) -> Dict[str, Any]:
    """
    Try to open a connection. Returns success or error message.
    Used by the /test-connection endpoint in main.py.
    """
    try:
        conn = get_connection(config)
        conn.close()
        return {"success": True}

    except mysql.connector.Error as e:
        logger.error(f"MySQL connection failed: {e}")
        return {"success": False, "error": f"MySQL Error: {str(e)}"}

    except pyodbc.Error as e:
        logger.error(f"MSSQL connection failed: {e}")
        return {"success": False, "error": f"MSSQL Error: {str(e)}"}

    except Exception as e:
        logger.error(f"Connection failed: {e}")
        return {"success": False, "error": str(e)}


# ============================================================
#  2. GET SCHEMA
#  Reads all tables, columns, data types, and foreign keys.
#  This is sent to the AI so it knows your exact database structure.
# ============================================================

def get_schema(config) -> Dict[str, Any]:
    """
    Returns a dictionary like:
    {
      "tables": {
        "customers": {
          "columns": [
            {"name": "id", "type": "INT", "nullable": False},
            {"name": "name", "type": "VARCHAR(100)", "nullable": True},
          ],
          "primary_key": ["id"],
          "foreign_keys": []
        },
        ...
      }
    }
    """
    try:
        conn = get_connection(config)

        if config.db_type.lower() == "mysql":
            return _get_mysql_schema(conn, config.database)
        else:
            return _get_mssql_schema(conn, config.database)

    except Exception as e:
        logger.error(f"Schema fetch failed: {e}")
        return {"error": str(e)}


def _get_mysql_schema(conn, database: str) -> Dict[str, Any]:
    """Extract full schema from MySQL using information_schema."""
    cursor = conn.cursor(dictionary=True)
    schema = {"tables": {}}

    # ── Get all table names ───────────────────────────────────
    cursor.execute("""
        SELECT TABLE_NAME
        FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = %s AND TABLE_TYPE = 'BASE TABLE'
        ORDER BY TABLE_NAME
    """, (database,))
    tables = [row["TABLE_NAME"] for row in cursor.fetchall()]

    for table in tables:
        schema["tables"][table] = {"columns": [], "primary_key": [], "foreign_keys": []}

        # ── Get columns for this table ────────────────────────
        cursor.execute("""
            SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_KEY, CHARACTER_MAXIMUM_LENGTH
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
            ORDER BY ORDINAL_POSITION
        """, (database, table))

        for col in cursor.fetchall():
            col_type = col["DATA_TYPE"].upper()
            if col["CHARACTER_MAXIMUM_LENGTH"]:
                col_type += f"({col['CHARACTER_MAXIMUM_LENGTH']})"

            schema["tables"][table]["columns"].append({
                "name": col["COLUMN_NAME"],
                "type": col_type,
                "nullable": col["IS_NULLABLE"] == "YES"
            })

            # Track primary key columns
            if col["COLUMN_KEY"] == "PRI":
                schema["tables"][table]["primary_key"].append(col["COLUMN_NAME"])

        # ── Get foreign keys (relationships between tables) ───
        cursor.execute("""
            SELECT
                kcu.COLUMN_NAME,
                kcu.REFERENCED_TABLE_NAME,
                kcu.REFERENCED_COLUMN_NAME
            FROM information_schema.KEY_COLUMN_USAGE kcu
            JOIN information_schema.TABLE_CONSTRAINTS tc
                ON kcu.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
                AND kcu.TABLE_SCHEMA = tc.TABLE_SCHEMA
            WHERE tc.CONSTRAINT_TYPE = 'FOREIGN KEY'
                AND kcu.TABLE_SCHEMA = %s
                AND kcu.TABLE_NAME = %s
        """, (database, table))

        for fk in cursor.fetchall():
            schema["tables"][table]["foreign_keys"].append({
                "column": fk["COLUMN_NAME"],
                "references_table": fk["REFERENCED_TABLE_NAME"],
                "references_column": fk["REFERENCED_COLUMN_NAME"]
            })

    cursor.close()
    conn.close()
    return schema


def _get_mssql_schema(conn, database: str) -> Dict[str, Any]:
    """Extract full schema from Microsoft SQL Server using sys tables."""
    cursor = conn.cursor()
    schema = {"tables": {}}

    # ── Get all user tables ───────────────────────────────────
    cursor.execute("""
        SELECT TABLE_NAME
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_TYPE = 'BASE TABLE'
        ORDER BY TABLE_NAME
    """)
    tables = [row[0] for row in cursor.fetchall()]

    for table in tables:
        schema["tables"][table] = {"columns": [], "primary_key": [], "foreign_keys": []}

        # ── Get columns ───────────────────────────────────────
        cursor.execute("""
            SELECT
                c.COLUMN_NAME,
                c.DATA_TYPE,
                c.IS_NULLABLE,
                c.CHARACTER_MAXIMUM_LENGTH,
                CASE WHEN pk.COLUMN_NAME IS NOT NULL THEN 'PRI' ELSE '' END AS COLUMN_KEY
            FROM INFORMATION_SCHEMA.COLUMNS c
            LEFT JOIN (
                SELECT ku.COLUMN_NAME
                FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
                JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE ku
                    ON tc.CONSTRAINT_NAME = ku.CONSTRAINT_NAME
                WHERE tc.CONSTRAINT_TYPE = 'PRIMARY KEY' AND tc.TABLE_NAME = ?
            ) pk ON c.COLUMN_NAME = pk.COLUMN_NAME
            WHERE c.TABLE_NAME = ?
            ORDER BY c.ORDINAL_POSITION
        """, (table, table))

        for col in cursor.fetchall():
            col_type = col[1].upper()
            if col[3]:  # CHARACTER_MAXIMUM_LENGTH
                col_type += f"({col[3]})"

            schema["tables"][table]["columns"].append({
                "name": col[0],
                "type": col_type,
                "nullable": col[2] == "YES"
            })

            if col[4] == "PRI":
                schema["tables"][table]["primary_key"].append(col[0])

        # ── Get foreign keys ──────────────────────────────────
        cursor.execute("""
            SELECT
                fk_col.COLUMN_NAME,
                pk_tab.TABLE_NAME AS referenced_table,
                pk_col.COLUMN_NAME AS referenced_column
            FROM INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS rc
            JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE fk_col
                ON rc.CONSTRAINT_NAME = fk_col.CONSTRAINT_NAME
            JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE pk_col
                ON rc.UNIQUE_CONSTRAINT_NAME = pk_col.CONSTRAINT_NAME
            JOIN INFORMATION_SCHEMA.TABLE_CONSTRAINTS pk_tab
                ON rc.UNIQUE_CONSTRAINT_NAME = pk_tab.CONSTRAINT_NAME
            WHERE fk_col.TABLE_NAME = ?
        """, (table,))

        for fk in cursor.fetchall():
            schema["tables"][table]["foreign_keys"].append({
                "column": fk[0],
                "references_table": fk[1],
                "references_column": fk[2]
            })

    cursor.close()
    conn.close()
    return schema


# ============================================================
#  3. EXECUTE QUERY
#  Runs a SQL string against the database and returns rows.
# ============================================================

def execute_query(config, sql: str) -> Dict[str, Any]:
    """
    Execute a SQL query and return results as a list of dicts.

    Returns:
    {
      "columns": ["id", "name", "revenue"],
      "rows": [{"id": 1, "name": "Alice", "revenue": 5000}, ...],
      "row_count": 1
    }
    """
    try:
        conn = get_connection(config)

        if config.db_type.lower() == "mysql":
            # dictionary=True makes each row a dict {column: value}
            cursor = conn.cursor(dictionary=True)
        else:
            cursor = conn.cursor()

        logger.info(f"Executing SQL: {sql}")
        cursor.execute(sql)

        rows_raw = cursor.fetchall()

        # ── Extract column names ──────────────────────────────
        columns = [desc[0] for desc in cursor.description] if cursor.description else []

        # ── For MSSQL rows are tuples — convert to dicts ──────
        if config.db_type.lower() == "mssql":
            rows = [dict(zip(columns, row)) for row in rows_raw]
        else:
            rows = rows_raw  # MySQL already returns dicts

        # ── Convert any non-serializable types (dates etc.) ───
        rows = _serialize_rows(rows)

        cursor.close()
        conn.close()

        return {
            "columns": columns,
            "rows": rows,
            "row_count": len(rows)
        }

    except mysql.connector.Error as e:
        logger.error(f"MySQL query error: {e}")
        return {"error": f"MySQL Error: {str(e)}"}

    except pyodbc.Error as e:
        logger.error(f"MSSQL query error: {e}")
        return {"error": f"MSSQL Error: {str(e)}"}

    except Exception as e:
        logger.error(f"Query execution failed: {e}")
        return {"error": str(e)}


def _serialize_rows(rows):
    """
    Convert Python objects that JSON cannot handle:
      datetime → string
      Decimal  → float
      bytes    → string
    """
    import datetime
    import decimal

    serialized = []
    for row in rows:
        clean = {}
        for k, v in row.items():
            if isinstance(v, (datetime.date, datetime.datetime)):
                clean[k] = v.isoformat()
            elif isinstance(v, decimal.Decimal):
                clean[k] = float(v)
            elif isinstance(v, bytes):
                clean[k] = v.decode("utf-8", errors="replace")
            else:
                clean[k] = v
        serialized.append(clean)
    return serialized
