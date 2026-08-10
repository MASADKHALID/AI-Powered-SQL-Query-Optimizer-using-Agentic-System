# ============================================================
#  ai_agent.py — Google Gemini API Version (FREE)
#
#  Gemini is 100% free — no credit card needed
#  Sign up: https://aistudio.google.com
#  Then: Get API Key → Create Key → paste below
#
#  Only ONE thing to change:
#    GEMINI_API_KEY = "paste-your-gemini-key-here"
# ============================================================

import time

import requests
import re
import logging
from typing import Tuple

logger = logging.getLogger(__name__)
'''
# ============================================================
GEMINI_API_KEY = "AQ.Ab8RN6KrTfk75IK0A32Zkc-qp_xyTJW1JPFPs_EhIB8uKfcMBQ"

# Gemini API settings — do not change these
GEMINI_URL   = "https://generativelanguage.googleapis.com/v1beta/models"
GEMINI_MODEL = "gemini-2.0-flash"   # free, fast, good for SQL
'''
OPENROUTER_KEY   = "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"
OPENROUTER_URL   = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = "openrouter/free"
# ============================================================
#  SCHEMA FORMATTER
#  Converts schema dict to readable text for the AI
# ============================================================

def schema_to_text(schema: dict) -> str:
    """Convert schema dict to readable text."""
    lines = []
    tables = schema.get("tables", {})

    for table_name, table_info in tables.items():
        lines.append(f"Table: {table_name}")
        for col in table_info.get("columns", []):
            pk       = " [PRIMARY KEY]" if col["name"] in table_info.get("primary_key", []) else ""
            nullable = "" if col["nullable"] else " NOT NULL"
            lines.append(f"  - {col['name']} ({col['type']}){nullable}{pk}")
        for fk in table_info.get("foreign_keys", []):
            lines.append(f"  - FK: {fk['column']} → {fk['references_table']}.{fk['references_column']}")
        lines.append("")

    result = "\n".join(lines)
    # Trim schema if too long for API token limit
    if len(result) > 2000:
        result = result[:2000] + "\n...(truncated)"
    return result


# ============================================================
#  GENERATE SQL — main function called by main.py
# ============================================================
def generate_sql(question: str, schema: dict, db_type: str, model: str = None) -> Tuple[str, str]:
    """
    Send question + schema to OpenRouter API.
    Returns SQL + explanation in ONE single API call.
    """
    time.sleep(3)
    schema_text = schema_to_text(schema)

    if db_type.lower() == "mysql":
        syntax = "MySQL syntax. Use backticks for identifiers. Use LIMIT for row limits."
    elif db_type.lower() == "mssql":
        syntax = "T-SQL syntax. Use square brackets for identifiers. Use TOP instead of LIMIT."
    else:
        syntax = "Standard SQL syntax."

    # Single prompt — gets SQL + explanation in one call
    full_prompt = f"""You are an expert SQL query generator.
Database type: {db_type.upper()}
Syntax rules: {syntax}

DATABASE SCHEMA:
{schema_text}

RULES:
1. Use EXACT table and column names from schema
2. Use proper JOINs when multiple tables needed
3. SELECT queries by default. Only generate INSERT/UPDATE/DELETE if user explicitly asks to add, update or delete data.
4. Add TOP 1000 (MSSQL) or LIMIT 1000 (MySQL) by default

USER QUESTION: {question}

Respond ONLY in this exact format — nothing else:
SQL: <the sql query here>
EXPLANATION: <one sentence plain English explanation here>"""

    logger.info(f"Calling OpenRouter for: {question}")

    try:
        response = requests.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {OPENROUTER_KEY}",
                "Content-Type":  "application/json",
                "HTTP-Referer":  "http://localhost:8000",
                "X-Title":       "SQL Assistant"
            },
            json={
                "model":       OPENROUTER_MODEL,
                "messages":    [{"role": "user", "content": full_prompt}],
                "temperature": 0.1,
                "max_tokens":  1024
            },
            timeout=30
        )
        response.raise_for_status()

        raw = response.json()["choices"][0]["message"]["content"].strip()
        logger.info(f"OpenRouter raw output: {raw[:200]}")

        # Parse SQL and EXPLANATION from single response
        sql         = ""
        explanation = ""

        for line in raw.split("\n"):
            line = line.strip()
            if line.upper().startswith("SQL:"):
                sql = line[4:].strip()
            elif line.upper().startswith("EXPLANATION:"):
                explanation = line[12:].strip()

        # Fallback — if format not followed treat whole thing as SQL
        if not sql:
            sql = clean_sql(raw)

        if not explanation:
            explanation = f"Retrieves data for: {question}"

        sql = clean_sql(sql) if sql else ""

        if not sql:
            return "", "Could not generate a valid SQL query."

        return sql, explanation

    except requests.exceptions.ConnectionError:
        raise Exception("Cannot connect to OpenRouter. Check your internet connection.")

    except requests.exceptions.HTTPError as e:
        status = e.response.status_code
        if status == 400:
            raise Exception("OpenRouter bad request — check your API key.")
        elif status == 401:
            raise Exception("Invalid OpenRouter key. Get free key at https://openrouter.ai")
        elif status == 404:
            raise Exception("OpenRouter model not found — check OPENROUTER_MODEL in ai_agent.py")
        elif status == 429:
            raise Exception("OpenRouter rate limit reached. Wait a moment and try again.")
        else:
            raise Exception(f"OpenRouter error {status}: {str(e)}")

    except KeyError:
        raise Exception("Unexpected response from OpenRouter API.")

    except Exception as e:
        raise Exception(f"AI error: {str(e)}")
'''
def generate_sql(question: str, schema: dict, db_type: str, model: str = None) -> Tuple[str, str]:
    """
    Send question + schema to Groq API.
    Groq runs llama3 for free — no cost, no limits for testing.
    Returns (sql_query, explanation).
    """
    time.sleep(2)
    schema_text = schema_to_text(schema)

    # Syntax rules per database type
    if db_type.lower() == "mysql":
        syntax = "MySQL syntax. Use backticks for identifiers. Use LIMIT for row limits."
    elif db_type.lower() == "mssql":
        syntax = "T-SQL syntax. Use square brackets for identifiers. Use TOP instead of LIMIT."
    else:
        syntax = "Standard SQL syntax."

    system_prompt = f"""You are an expert SQL query generator.
Database type: {db_type.upper()}
Syntax rules: {syntax}

DATABASE SCHEMA:
{schema_text}

STRICT RULES:
1. Output ONLY the SQL query — no explanation, no markdown, no backticks
2. Use EXACT table and column names from the schema above
3. Use proper JOINs when data from multiple tables is needed
4. Use table aliases for readability (c for customers, o for orders etc.)
5. Add TOP 1000 (MSSQL) or LIMIT 1000 (MySQL) unless user asks for all
6. Only SELECT queries — never DELETE, DROP, INSERT, UPDATE, CREATE
7. If question cannot be answered write: -- Cannot answer: reason"""

    logger.info(f"Calling Gemini API for: {question}")

    try:
        url = f"{GEMINI_URL}/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"

        response = requests.post(
            url,
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{
                    "parts": [{"text": system_prompt + "\n\nGenerate SQL for: " + question}]
                }],
                "generationConfig": {
                    "temperature":     0.1,
                    "maxOutputTokens": 1024,
                    "topP":            0.9
                }
            },
            timeout=30
        )
        response.raise_for_status()
        raw = response.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        logger.info(f"Gemini raw output: {raw[:150]}")
        sql = clean_sql(raw)
        if not sql:
            logger.warning("Gemini returned empty or invalid SQL")
            return "", "Could not generate a valid SQL query."
        explanation = get_explanation(question, sql)
        return sql, explanation

    except requests.exceptions.ConnectionError:
        raise Exception("Cannot connect to Gemini API. Check your internet connection.")

    except requests.exceptions.HTTPError as e:
        status = e.response.status_code
        if status == 400:
            raise Exception("Gemini API bad request — check your API key.")
        elif status == 403:
            raise Exception("Invalid Gemini API key. Get free key at https://aistudio.google.com")
        elif status == 404:
            raise Exception("Gemini model not found — check GEMINI_MODEL in ai_agent.py")
        elif status == 429:
            raise Exception("Gemini rate limit reached. Wait a moment and try again.")
        else:
            raise Exception(f"Gemini API error {status}: {str(e)}")

    except KeyError:
        raise Exception("Unexpected response from Gemini API.")
    
    except Exception as e:
        raise Exception(f"AI error: {str(e)}")


# ============================================================
#  GET EXPLANATION
#  Ask Groq to explain the SQL in plain English
# ============================================================

def get_explanation(question: str, sql: str, model: str = None) -> str:
    """Ask Groq to explain the SQL in one sentence."""
    try:
        url = f"{GEMINI_URL}/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
        response = requests.post(
            url,
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{
                    "parts": [{"text": f"In one clear sentence explain what this SQL query returns in plain English. No technical jargon.\nQuestion: {question}\nSQL: {sql}\nExplanation:"}]
                }],
                "generationConfig": {"temperature": 0.3, "maxOutputTokens": 100}
            },
            timeout=15
        )
        response.raise_for_status()
        text = response.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        return text.split(".")[0].strip() + "."

    except Exception:
        # Explanation is optional — don't fail if this doesn't work
        return f"Retrieves data for: {question}"

'''
# ============================================================
#  SQL CLEANER
#  Removes markdown, backticks, extra text from AI output
# ============================================================

def clean_sql(raw: str) -> str:
    """Strip markdown and extra text — return clean SQL only."""
    # Remove ```sql ... ``` blocks
    raw = re.sub(r"```sql\s*", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"```\s*",    "", raw)

    lines     = raw.strip().split("\n")
    sql_lines = []

    for line in lines:
        stripped = line.strip()
        if sql_lines and stripped and not stripped.startswith("--") and \
           not any(stripped.upper().startswith(kw) for kw in [
               "SELECT", "WITH", "FROM", "WHERE", "JOIN", "LEFT", "RIGHT",
               "INNER", "OUTER", "FULL", "CROSS", "GROUP", "ORDER", "HAVING",
               "LIMIT", "TOP", "UNION", "--", ")", "AND", "OR", "ON", "AS",
               "CASE", "WHEN", "THEN", "ELSE", "END"
           ]):
            if not any(c in stripped for c in ["(", ".", ",", "=", "<", ">", "'"]):
                break
        sql_lines.append(line)

    sql = "\n".join(sql_lines).strip().rstrip(";").strip()
    return sql if sql.upper().startswith(("SELECT", "WITH", "--")) else ""
