import sqlite3
import pandas as pd
import requests
import json

# 0. CONFIGURATION ###################################

MODEL = "smollm2:1.7b"
PORT = 11434
OLLAMA_HOST = f"http://localhost:{PORT}"
CHAT_URL = f"{OLLAMA_HOST}/api/chat"
DB_PATH = "ice_news.db"

# 1. DATABASE CONNECTION ###################################

conn = sqlite3.connect(DB_PATH)

# 2. SEARCH FUNCTION ###################################

def search_documents(query, db_connection, limit=5):
    """
    Search ICE-related articles and state metrics relevant to the query.

    Parameters:
    -----------
    query : str
        The search term to look for
    db_connection : sqlite3.Connection
        Database connection object
    limit : int
        Maximum number of article results to return

    Returns:
    --------
    dict
        Dictionary containing matching articles and state metrics
    """

    search_pattern = f"%{query}%"

    # Search articles
    article_sql = """
        SELECT headline, source, published_at, url, state, city, county, region_type, topic_tags, snippet
        FROM articles
        WHERE headline LIKE ?
           OR snippet LIKE ?
           OR topic_tags LIKE ?
           OR state LIKE ?
           OR city LIKE ?
           OR county LIKE ?
        ORDER BY published_at DESC
        LIMIT ?
    """

    articles_df = pd.read_sql_query(
        article_sql,
        db_connection,
        params=(
            search_pattern,
            search_pattern,
            search_pattern,
            search_pattern,
            search_pattern,
            search_pattern,
            limit
        )
    )

    # Search state metrics
    metrics_sql = """
        SELECT state, state_abbr, ice_facility_count, foreign_born_pct, non_citizen_pct, total_population, notes
        FROM state_metrics
        WHERE state LIKE ?
           OR state_abbr LIKE ?
           OR notes LIKE ?
    """

    metrics_df = pd.read_sql_query(
        metrics_sql,
        db_connection,
        params=(search_pattern, search_pattern, search_pattern)
    )

    return {
        "articles": articles_df.to_dict(orient="records"),
        "state_metrics": metrics_df.to_dict(orient="records")
    }


def print_retrieval_preview(data, title):
    """Compact preview of retrieved rows (like 04_sqlite.py test output)."""
    print(title)
    if data["articles"]:
        art_df = pd.DataFrame(data["articles"])
        cols = [c for c in ("headline", "published_at", "state", "source") if c in art_df.columns]
        print(art_df[cols].to_string(index=False))
    else:
        print("  (no articles)")
    print()
    if data["state_metrics"]:
        met_df = pd.DataFrame(data["state_metrics"])
        cols = [c for c in ("state", "state_abbr", "ice_facility_count") if c in met_df.columns]
        print(met_df[cols].to_string(index=False))
    else:
        print("  (no state metrics)")
    print()


# 3. TEST SEARCH FUNCTION ###################################

print("Testing search function...")
test_result = search_documents("Texas", conn, limit=3)
n_art = len(test_result["articles"])
n_met = len(test_result["state_metrics"])
print(f"Found {n_art} matching articles, {n_met} state metric rows")
print_retrieval_preview(test_result, "Search preview (tiny table):")

# 4. RAG WORKFLOW ###################################
# Task 3: test the full pipeline with multiple queries (natural question + DB search term).

RAG_QUERIES = [
    (
        "What has been happening in Texas lately?",
        "Texas",
    ),
    (
        "What do the retrieved items say about ICE detention, custody, or deaths?",
        "custody",
    ),
    (
        "Is there coverage of airports, TSA, or Houston?",
        "airport",
    ),
]

role = """
You are a data reporter for an ICE and demographics dashboard.

Use only the retrieved JSON records provided below.
Do not use outside knowledge.
Do not mention any facts, dates, incidents, or trends unless they appear explicitly in the JSON.
If the JSON includes relevant articles, summarize those articles directly.
Mention the article headlines, locations, and dates when helpful.
Use the state metrics only as supporting context.
If no relevant records were retrieved, say that clearly.
Write a concise, neutral, factual summary in about 4-6 sentences.
Do not make assumptions. Do not make up missing information.
"""

for i, (user_query, search_query) in enumerate(RAG_QUERIES, start=1):
    print("=" * 60)
    print(f"RAG query {i}/{len(RAG_QUERIES)}")
    print(f"  User question:  {user_query}")
    print(f"  Database search: {search_query!r}")
    print("=" * 60)

    retrieved_data = search_documents(search_query, conn, limit=3)
    retrieved_json = json.dumps(retrieved_data, indent=2)

    print_retrieval_preview(retrieved_data, "RAG retrieval preview (tiny table):")

    if len(retrieved_data["articles"]) == 0 and len(retrieved_data["state_metrics"]) == 0:
        print("📝 Generated Summary:")
        print("No relevant records were retrieved from the database for this query.")
        print()
        continue

    messages = [
        {"role": "system", "content": role},
        {
            "role": "user",
            "content": f"User question: {user_query}\n\nRetrieved JSON:\n{retrieved_json}"
        },
    ]

    body = {
        "model": MODEL,
        "messages": messages,
        "stream": False,
    }

    try:
        response = requests.post(CHAT_URL, json=body)
    except requests.exceptions.ConnectionError:
        print(
            f"Could not connect to Ollama at {CHAT_URL}.\n"
            "Start the Ollama desktop app, or run `ollama serve` in a terminal.\n"
            f"Ensure the model is available: `ollama pull {MODEL}`"
        )
        raise

    response.raise_for_status()
    response_data = response.json()

    result = response_data["message"]["content"]

    print("📝 Generated Summary:")
    print(result)
    print()

# 5. CLEANUP ###################################

conn.close()