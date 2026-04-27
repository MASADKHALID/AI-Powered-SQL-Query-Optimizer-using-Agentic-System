# ============================================================
#  SQL Assistant Backend — FastAPI
#  Supports: MySQL + Microsoft SQL Server (MSSQL)
#  AI:       Ollama (llama3 / sqlcoder running locally)
#  Author:   Your Name
# ============================================================

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import logging

# Import our own modules (files in this project)
from database import get_schema, execute_query, test_connection
#from ai_agent import generate_sql

# ── Logging setup ────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Create FastAPI app ───────────────────────────────────────
app = FastAPI(
    title="SQL Assistant API",
    description="Natural language to SQL — powered by Ollama + FastAPI",
    version="1.0.0"
)

# ── Allow the Chrome extension / frontend to call this API ───
# CORS = Cross-Origin Resource Sharing
# Without this the browser will block requests from the extension
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # In production replace * with your extension ID
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
#  REQUEST / RESPONSE MODELS
#  These define the shape of JSON sent to and from the API
# ============================================================

class ConnectionConfig(BaseModel):
    """Database connection details sent from the frontend."""
    db_type: str          # "mysql" or "mssql"
    host: str             # e.g. "localhost" or "192.168.1.10"
    port: Optional[int]   # MySQL default 3306 | MSSQL default 1433
    username: str
    password: str
    database: str         # The specific database/schema name to use

class QueryRequest(BaseModel):
    """A natural language question + connection config."""
    connection: ConnectionConfig
    question: str         # e.g. "show me top 10 customers by revenue"
    model: Optional[str] = "llama3"  # Ollama model name to use

class QueryResponse(BaseModel):
    """What we send back to the frontend."""
    sql: str                          # The generated SQL query
    results: List[Dict[str, Any]]     # Rows returned from the database
    columns: List[str]                # Column names for the table header
    row_count: int                    # How many rows were returned
    explanation: str                  # Plain English explanation of the query


# ============================================================
#  ROUTES (API Endpoints)
# ============================================================

@app.get("/")
def root():
    """Health check — visit http://localhost:8000/ to confirm server is running."""
    return {"status": "running", "message": "SQL Assistant API is live ✓"}


@app.post("/test-connection")
def api_test_connection(config: ConnectionConfig):
    """
    Step 1 — Test if the database credentials are correct.
    The frontend calls this when the user clicks 'Connect'.
    Returns success or an error message.
    """
    logger.info(f"Testing connection to {config.db_type} at {config.host}/{config.database}")
    result = test_connection(config)

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])

    return {"success": True, "message": f"Connected to '{config.database}' successfully ✓"}


@app.post("/schema")
def api_get_schema(config: ConnectionConfig):
    """
    Step 2 — Fetch the database schema (all tables + columns + types).
    The AI needs this to write accurate SQL with correct table/column names.
    """
    logger.info(f"Fetching schema from {config.db_type}/{config.database}")
    schema = get_schema(config)

    if "error" in schema:
        raise HTTPException(status_code=500, detail=schema["error"])

    return schema


@app.post("/query", response_model=QueryResponse)

def api_run_query(req: QueryRequest):
    """
    Main endpoint — takes a natural language question, generates SQL,
    executes it against the real database, and returns the results.

    Flow:
      1. Fetch schema  →  2. Send to Ollama AI  →  3. Execute SQL  →  4. Return results
    """
    logger.info(f"Question: '{req.question}' | DB: {req.connection.db_type}/{req.connection.database}")

    # ── Step 1: Get database schema for AI context ───────────
    schema = get_schema(req.connection)
    if "error" in schema:
        raise HTTPException(status_code=500, detail=f"Schema error: {schema['error']}")

    # ── Step 2: Ask Ollama AI to generate the SQL query ──────
    sql, explanation = generate_sql(
        question=req.question,
        schema=schema,
        db_type=req.connection.db_type,
        model=req.model
    )

    if not sql:
        raise HTTPException(status_code=500, detail="AI could not generate a valid SQL query.")

    logger.info(f"Generated SQL: {sql}")

    # ── Step 3: Execute the generated SQL on the real database ─
    result = execute_query(req.connection, sql)

    if "error" in result:
        raise HTTPException(status_code=400, detail=f"Query execution error: {result['error']}")

    # ── Step 4: Return everything to the frontend ─────────────
    return QueryResponse(
        sql=sql,
        results=result["rows"],
        columns=result["columns"],
        row_count=result["row_count"],
        explanation=explanation
    )


@app.post("/execute-sql")
def api_execute_raw_sql(config: ConnectionConfig, sql: str):
    """
    Optional — Execute a raw SQL query directly (user typed SQL manually).
    Only SELECT queries are allowed for safety.
    """
    # Safety check — only allow SELECT statements, never DELETE/DROP etc.
    sql_clean = sql.strip().upper()
    if not sql_clean.startswith("SELECT") and not sql_clean.startswith("WITH"):
        raise HTTPException(
            status_code=403,
            detail="Only SELECT queries are allowed for safety."
        )

    result = execute_query(config, sql)

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return result
