from flask import Flask, render_template, request, redirect, url_for, send_file
from models.db import get_connection
from utils.pdf_generator import generate_invoice_pdf
import os

app = Flask(__name__)
app.secret_key = 'your_secret_key'

@app.route('/')
def index():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM hotels")
    hotels = cursor.fetchall()
    conn.close()
    return render_template('index.html', hotels=hotels)

@app.route('/hotel/<int:hotel_id>')
def hotel_detail(hotel_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM hotels WHERE id=%s", (hotel_id,))
    hotel = cursor.fetchone()
    cursor.execute("SELECT * FROM rooms WHERE hotel_id=%s", (hotel_id,))
    rooms = cursor.fetchall()
    conn.close()
    return render_template('hotel_detail.html', hotel=hotel, rooms=rooms)

@app.route('/book/<int:room_id>', methods=['GET', 'POST'])
def book_room(room_id):
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        checkin = request.form['checkin']
        checkout = request.form['checkout']
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO bookings (room_id, name, email, checkin, checkout) VALUES (%s, %s, %s, %s, %s)",
                       (room_id, name, email, checkin, checkout))
        booking_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return redirect(url_for('invoice', booking_id=booking_id))
    return render_template('book.html', room_id=room_id)

@app.route('/invoice/<int:booking_id>')
def invoice(booking_id):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT b.id, b.name, b.email, b.checkin, b.checkout, r.price, h.name
            FROM bookings b
            JOIN rooms r ON b.room_id = r.id
            JOIN hotels h ON r.hotel_id = h.id
            WHERE b.id = %s
        """, (booking_id,))
        booking = cursor.fetchone()
        conn.close()

        if not booking:
            return "Booking not found", 404

        # Generate the invoice PDF
        pdf_path = generate_invoice_pdf(booking, booking_id)
        if not pdf_path or not os.path.exists(pdf_path):
            print(f"Error: PDF generation failed for booking ID {booking_id}")
            return "Error generating the invoice.", 500
        
        return send_file(pdf_path, as_attachment=True)
    
    except Exception as e:
        print(f"Error generating invoice: {e}")
        return "Error generating the invoice, please try again later.", 500

if __name__ == '__main__':
    app.run(debug=True)
