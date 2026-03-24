import sqlite3
import pandas as pd
import requests
import json

# configuration
MODEL = "smollm2:1.7b"
PORT = 11434
OLLAMA_HOST = f"http://localhost:{PORT}"
CHAT_URL = f"{OLLAMA_HOST}/api/chat"
DB_PATH = "ice_news.db"

# connect to database
conn = sqlite3.connect(DB_PATH)

def search_documents(query, db_connection, limit=5):
    """
    Search ICE-related articles and state metrics relevant to the query.
    """

    search_pattern = f"%{query}%"

    # search articles
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

    # search state metrics
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

# test search function
print("testing search function...")
test_result = search_documents("Texas", conn, limit=3)
print(json.dumps(test_result, indent=2))
print()

# example user query
user_query = "What has been happening in Texas lately?"

# retrieve relevant records
retrieved_data = search_documents(user_query, conn, limit=3)
retrieved_json = json.dumps(retrieved_data, indent=2)

# system prompt
role = """
You are a data reporter for an ICE and demographics dashboard.

Use only the retrieved JSON records provided to you.
Summarize what has been happening based on the articles.
Mention where and when events were reported.
Use the state metrics when helpful for context.
Do not invent facts, incidents, or statistics not included in the data.
If the data is limited, say so clearly. Do not make up any information. Do not make any assumptions.
Present information as neutral and objective as possible. No opinion or bias or political affiliation (left or right).
Write clearly and concisely.
"""

# send to ollama
messages = [
    {"role": "system", "content": role},
    {"role": "user", "content": f"User question: {user_query}\n\nRetrieved data:\n{retrieved_json}"}
]

body = {
    "model": MODEL,
    "messages": messages,
    "stream": False
}

response = requests.post(CHAT_URL, json=body)
response.raise_for_status()
response_data = response.json()

result = response_data["message"]["content"]

print("generated response:")
print(result)

conn.close()