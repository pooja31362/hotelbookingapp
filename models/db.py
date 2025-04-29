
import mysql.connector

def get_connection():
    try:
        conn = mysql.connector.connect(
            host="hoteldb.cf6me2usaddu.ap-south-1.rds.amazonaws.com",
            user="admin",
            password="Muthupattan1403",
            database="poojudb"
        )
        print("✅ Database connection successful")
        return conn
    except mysql.connector.Error as e:
        print(f"❌ Database connection failed: {e}")
        return None

