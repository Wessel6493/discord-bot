import mysql.connector
from mysql.connector import Error

try:
    connection = mysql.connector.connect(
        host="sql.freedb.tech",       
        user="'freedb_Wessel Laks'", 
        password="#$nsBRZYemEAW7h",
        database="freedb_discord_bot_db" 
    )

    if connection.is_connected():
        print("✅ Verbonden met de database!")

        cursor = connection.cursor()
        cursor.execute("SELECT DATABASE();")
        record = cursor.fetchone()
        print("Je zit nu in database:", record)

except Error as e:
    print("❌ Fout bij verbinden:", e)

finally:
    if 'connection' in locals() and connection.is_connected():
        connection.close()
        print("Verbinding gesloten")
