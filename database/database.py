import os
import mysql.connector
from mysql.connector import Error
from dotenv import load_dotenv
from datetime import datetime, timezone

load_dotenv()

# --------------------
# Database connectie
# --------------------
def create_db_connection():
    try:
        connection = mysql.connector.connect(
            host=os.getenv("DB_HOST"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASS"),
            database=os.getenv("DB_NAME")
        )
        if connection.is_connected():
            print("✅ Verbonden met database")
            return connection
    except Error as e:
        print("DB error:", e)
        return None

# --------------------
# Event functies
# --------------------
def get_event(connection, event_id):
    """
    Haal event op op basis van event_id
    """
    try:
        cursor = connection.cursor(dictionary=True)
        query = "SELECT * FROM announced_events WHERE event_id = %s AND deleted = 0"
        cursor.execute(query, (event_id,))
        result = cursor.fetchone()
        print(f"🔍 Gezocht naar event_id={event_id}, gevonden: {result} record(s)")
        return result
    except Exception as e:
        print(f"❌ get_event error (event_id={event_id}): {e}")
        return None

def insert_event(connection, event_id, message_id, event_name, location, occurance_time):
    """
    Voeg een nieuw event toe
    """
    cursor = connection.cursor()
    now_utc = datetime.now(timezone.utc)
    query = """
    INSERT INTO announced_events 
    (event_id, message_id, event_name, location, reminder_sent, created_at, occurance_time, deleted)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """
    try:
        cursor.execute(query, (
            event_id,
            message_id,
            event_name,
            location,
            None,          # reminder_sent
            now_utc,       # created_at
            occurance_time,
            0              # deleted = false
        ))
        connection.commit()
        return True
    except Error as e:
        print("DB insert error:", e)
        return False

def update_reminder(connection, event_id):
    """
    Markeer reminder als verzonden
    """
    cursor = connection.cursor()
    now_utc = datetime.now(timezone.utc)
    query = "UPDATE announced_events SET reminder_sent = %s WHERE event_id = %s"
    try:
        cursor.execute(query, (now_utc, event_id))
        connection.commit()
        return True
    except Error as e:
        print("DB update error:", e)
        return False