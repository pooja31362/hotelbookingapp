import pymysql
from config import DB_CONFIG  # Make sure this imports correctly from config.py

def get_connection():
    try:
        connection = pymysql.connect(
            host=DB_CONFIG['host'],
            user=DB_CONFIG['user'],
            password=DB_CONFIG['password'],
            db=DB_CONFIG['db'],
            port=DB_CONFIG['port']
        )
        return connection
    except Exception as e:
        print(f"Error connecting to database: {e}")
        return None


DB_CONFIG = {
    'host': 'hoteldb.cf6me2usaddu.ap-south-1.rds.amazonaws.com',
    'user': 'admin',
    'password': 'Muthupattan1403',
    'db': 'hoteldb',
    'port':'3306'
}

