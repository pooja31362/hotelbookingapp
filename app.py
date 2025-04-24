from flask import Flask, render_template, request, redirect, url_for, send_file
from models.db import get_connection
from utils.pdf_generator import generate_invoice_pdf
import os
from flask import session
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime,date, timedelta
from flask import flash
from flask import flash, redirect, url_for

app = Flask(__name__)
app.secret_key = 'your_secret_key'

@app.route('/')
def index():
    search = request.args.get('search')
    checkin = request.args.get('checkin')
    checkout = request.args.get('checkout')
    guests = request.args.get('guests', type=int)
    rooms = request.args.get('rooms', type=int)
    room_type = request.args.get('room_temp')
    min_price = request.args.get('min_price', type=float)
    max_price = request.args.get('max_price', type=float)
    features = request.args.getlist('features')

    if checkin and checkout:
        session['checkin'] = checkin
        session['checkout'] = checkout
    if guests:
        session['guest_count'] = guests

    conn = get_connection()
    cursor = conn.cursor()

    query = "SELECT DISTINCT h.* FROM hotels h JOIN rooms r ON h.id = r.hotel_id"
    filters = []
    params = []

    if search:
        filters.append("(h.name LIKE %s OR h.location LIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])
    if guests:
        if guests > 5:
            flash("Maximum 5 guests are allowed per room.")
            return redirect(url_for('index'))
        filters.append("r.guest_capacity >= %s")
        filters.append("r.guest_capacity <= 5")
        params.append(guests)
    if rooms:
        filters.append("r.available = TRUE")
    if room_type:
        filters.append("r.room_type = %s")
        params.append(room_type)
    if min_price:
        filters.append("r.price >= %s")
        params.append(min_price)
    if max_price:
        filters.append("r.price <= %s")
        params.append(max_price)
    if features:
        for feature in features:
            filters.append("r.features LIKE %s")
            params.append(f"%{feature}%")

    if filters:
        query += " WHERE " + " AND ".join(filters)

    cursor.execute(query, tuple(params))
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
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        govt_id = request.form['govt_id']

        checkin = session.get('checkin')
        checkout = session.get('checkout')
        guest_count = session.get('guest_count', 1)

        # ✅ Date format check
        try:
            checkin_date = datetime.strptime(checkin, "%Y-%m-%d")
            checkout_date = datetime.strptime(checkout, "%Y-%m-%d")
            if checkout_date <= checkin_date:
                return "Error: Check-out date must be after check-in date.", 400
        except Exception as e:
            return "Error: Invalid check-in/check-out format", 400

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO bookings (room_id, name, email, phone, guest_count, govt_id, checkin, checkout, user_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (room_id, name, email, phone, guest_count, govt_id, checkin, checkout, session['user_id']))
        
        booking_id = cursor.lastrowid

        # Save co-customers
        for i in range(1, int(guest_count)):
            co_name = request.form.get(f'co_name_{i}')
            co_age = request.form.get(f'co_age_{i}')
            if co_name and co_age:
                cursor.execute("INSERT INTO co_customers (booking_id, name, age) VALUES (%s, %s, %s)",
                               (booking_id, co_name, co_age))

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
            SELECT b.id, b.name, b.email, b.checkin, b.checkout, r.price,
                   h.name, b.phone,b.guest_count
            FROM bookings b
            JOIN rooms r ON b.room_id = r.id
            JOIN hotels h ON r.hotel_id = h.id
            WHERE b.id = %s
        """, (booking_id,))
        booking = cursor.fetchone()
        conn.close()

        if not booking:
            print(f"No booking found for ID {booking_id}")
            return "Booking not found", 404

        print("Fetched Booking Info:", booking)

        # Generate the invoice PDF
        pdf_path = generate_invoice_pdf(booking, booking_id)

        if not pdf_path or not os.path.exists(pdf_path):
            print(f"PDF not created or found at path: {pdf_path}")
            return "Error generating the invoice.", 500  #-----------------I AM GETTING STUCKED HERE_------# 

        print(f"Sending invoice file: {pdf_path}")
        return send_file(pdf_path, as_attachment=True)

    except Exception as e:
        print(f"Error generating invoice: {e}")
        return f"Error generating the invoice: {e}", 500 


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = generate_password_hash(request.form['password'])

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (username, email, password) VALUES (%s, %s, %s)", 
                       (username, email, password))
        conn.commit()
        conn.close()
        return redirect(url_for('login'))
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, password FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user[2], password):
            session['user_id'] = user[0]
            session['username'] = user[1]
            return redirect(url_for('index'))
        return "Invalid credentials"
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/history')
def booking_history():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT b.id, h.name, h.location, b.checkin, b.checkout, r.price
        FROM bookings b
        JOIN rooms r ON b.room_id = r.id
        JOIN hotels h ON r.hotel_id = h.id
        WHERE b.user_id = %s
        ORDER BY b.checkin DESC
    """, (user_id,))
    history = cursor.fetchall()
    conn.close()

    # ✅ Pass 'timedelta' to template
    return render_template('history.html', history=history, today=date.today(), timedelta=timedelta)

@app.route('/cancel/<int:booking_id>', methods=['POST'])
def cancel_booking(booking_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT b.checkin, b.user_id, b.room_id
        FROM bookings b
        WHERE b.id = %s
    """, (booking_id,))
    booking = cursor.fetchone()

    if not booking:
        flash("Booking not found.")
        conn.close()
        return redirect(url_for('booking_history'))

    checkin_date = booking[0]
    booking_user_id = booking[1]
    room_id = booking[2]

    if booking_user_id != session['user_id']:
        flash("You are not authorized to cancel this booking.")
        conn.close()
        return redirect(url_for('booking_history'))

    if checkin_date - datetime.today().date() < timedelta(days=1):
        flash("Cancellation not allowed within 24 hours of check-in.")
        conn.close()
        return redirect(url_for('booking_history'))

    # Delete co-customers
    cursor.execute("DELETE FROM co_customers WHERE booking_id = %s", (booking_id,))

    # Delete booking
    cursor.execute("DELETE FROM bookings WHERE id = %s", (booking_id,))

    # Optionally set room available (if your logic marks it unavailable)
    cursor.execute("UPDATE rooms SET available = TRUE WHERE id = %s", (room_id,))

    conn.commit()
    conn.close()

    flash("Booking cancelled successfully.")
    return redirect(url_for('booking_history'))
if __name__ == '__main__':
    app.run(debug=True)
