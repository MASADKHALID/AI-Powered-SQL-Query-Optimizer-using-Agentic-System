# ============================================================
#  main.py — FastAPI Backend
#  Now includes AGENTIC AI endpoint alongside normal endpoint
# ============================================================

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import logging

from database import get_schema, execute_query, test_connection
from ai_agent import generate_sql          # original one-shot AI
#from ai_agent import run_agent                # NEW — agentic AI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="SQL Assistant API — Agentic",
    description="Natural language to SQL with Agentic AI",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response Models ────────────────────────────────
'''
class ConnectionConfig(BaseModel):
    db_type: str
    host: str
    port: Optional[int]
    username: str
    password: str
    database: str
    #excel
    file_path: str
'''
class ConnectionConfig(BaseModel):
    db_type: str
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None
    database: Optional[str] = None
    file_path: Optional[str] = None
    
class QueryRequest(BaseModel):
    connection: ConnectionConfig
    question: str
    model: Optional[str] = "sqlcoder"
    use_agent: Optional[bool] = True   # True = agentic, False = simple

class QueryResponse(BaseModel):
    sql: str
    results: List[Dict[str, Any]]
    columns: List[str]
    row_count: int
    explanation: str
    thinking: Optional[List[str]] = []
    retries: Optional[int] = 0
    mode: Optional[str] = "agent"


# ── Endpoints ────────────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "running", "message": "SQL Assistant API v2.0 — Agentic Mode active"}


@app.post("/test-connection")
def api_test_connection(config: ConnectionConfig):
    result = test_connection(config)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return {"success": True, "message": f"Connected to '{config.database}' successfully"}


@app.post("/schema")
def api_get_schema(config: ConnectionConfig):
    schema = get_schema(config)
    if "error" in schema:
        raise HTTPException(status_code=500, detail=schema["error"])
    return schema


@app.post("/query", response_model=QueryResponse)
def api_run_query(req: QueryRequest):
    """
    Main endpoint — Agentic AI flow:
      Step 1: Agent understands the question
      Step 2: Agent identifies tables + joins needed
      Step 3: Agent generates SQL
      Step 4: Agent validates SQL
      Step 5: Agent runs SQL on real database
      Step 6: Agent retries if failed (up to 3x)
      Step 7: Agent explains results in plain English
    """
    logger.info(f"Question: '{req.question}' | Mode: {'AGENT' if req.use_agent else 'SIMPLE'}")

    schema = get_schema(req.connection)
    if "error" in schema:
        raise HTTPException(status_code=500, detail=f"Schema error: {schema['error']}")

    # ── AGENTIC MODE ─────────────────────────────────────────
    
    # ── SIMPLE MODE ───────────────────────────────────────────
    '''
    sql, explanation = generate_sql(
        question=req.question,
        schema=schema,
        db_type=req.connection.db_type,
        model=req.model
    )
    if not sql:
        raise HTTPException(status_code=500, detail="Could not generate SQL.")
    result = execute_query(req.connection, sql)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return QueryResponse(
        sql=sql,
        results=result["rows"],
        columns=result["columns"],
        row_count=result["row_count"],
        explanation=explanation,
        thinking=[],
        retries=0,
        mode="simple"
    )
    '''
    sql, explanation = generate_sql(
        question=req.question,
        schema=schema,
        db_type=req.connection.db_type,
        model=req.model
    )
    if not sql:
        raise HTTPException(status_code=500, detail="Could not generate SQL.")

    # For INSERT/UPDATE/DELETE — return SQL only, don't execute
    # User clicks Run button in frontend with password verification
    sql_upper = sql.strip().upper()
    if sql_upper.startswith(("INSERT", "UPDATE", "DELETE")):
        return QueryResponse(
            sql=sql,
            results=[],
            columns=[],
            row_count=0,
            explanation=explanation,
            thinking=[],
            retries=0,
            mode="simple"
        )

    # For SELECT — execute and return results
    result = execute_query(req.connection, sql)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return QueryResponse(
        sql=sql,
        results=result["rows"],
        columns=result["columns"],
        row_count=result["row_count"],
        explanation=explanation,
        thinking=[],
        retries=0,
        mode="simple"
    )


@app.post("/execute-sql")
def api_execute_raw_sql(config: ConnectionConfig, sql: str):
    """
    Execute a raw SQL query directly.
    Called when user clicks the RUN button in frontend.
    Only SELECT queries allowed for safety.
    """
    # Safety check — never allow dangerous queries
    sql_clean = sql.strip().upper()
    # Allow INSERT, UPDATE, DELETE only if password verified
    # Password check is done in frontend before calling this endpoint
    # Block only dangerous queries — allow SELECT, INSERT, UPDATE, DELETE
    dangerous = any(sql_clean.startswith(kw) for kw in ["DROP", "TRUNCATE", "ALTER", "CREATE", "EXEC"])
    if dangerous:
        raise HTTPException(
        status_code=403,
        detail="DROP, TRUNCATE, ALTER, CREATE queries are permanently blocked for safety."
        )
    logger.info(f"Executing raw SQL: {sql[:100]}")

    result = execute_query(config, sql)

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return {
        "columns":   result.get("columns", []),
        "rows":      result.get("rows", []),
        "row_count": result.get("row_count", 0),
        "sql":       sql
    }
