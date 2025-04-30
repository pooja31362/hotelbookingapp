from flask import Flask, render_template, request, redirect, url_for, send_file, abort
from models.db import get_connection
from utils.pdf_generator import generate_invoice_pdf
import os
from flask import session
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime,date, timedelta
from flask import flash, redirect, url_for

app = Flask(__name__)
app.secret_key = 'your_secret_key'

@app.route('/')
def index():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE rooms
        SET available = TRUE
        WHERE id IN (
            SELECT room_id
            FROM bookings
            WHERE checkout < CURDATE()
        )
    """)
    conn.commit()

    search = request.args.get('search')
    checkin = request.args.get('checkin')
    checkout = request.args.get('checkout')
    adults = request.args.get('adults', type=int)
    children = request.args.get('children', type=int)
    rooms = request.args.get('rooms', type=int)
    room_type = request.args.get('room_temp')
    min_price = request.args.get('min_price', type=float)
    max_price = request.args.get('max_price', type=float)
    features = request.args.getlist('features')

    if checkin and checkout:
        session['checkin'] = checkin
        session['checkout'] = checkout

    total_guests = (adults or 0) + (children or 0)

    if adults is not None:
        if adults < 1:
            flash("At least one adult is required for booking.")
            return redirect(url_for('index'))
        if adults > 5:
            flash("Maximum 5 adults allowed per room.")
            return redirect(url_for('index'))

    if total_guests > 5:
        flash("Total guests (adults + children) cannot exceed 5 per room.")
        return redirect(url_for('index'))

    session['guest_count'] = total_guests
    session['adults'] = adults
    session['children'] = children
    session['rooms'] = rooms  # ✅ Added this line

    query = "SELECT DISTINCT h.* FROM hotels h JOIN rooms r ON h.id = r.hotel_id"
    filters = []
    params = []

    if search:
        filters.append("(h.name LIKE %s OR h.location LIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])
    if total_guests:
        filters.append("r.guest_capacity >= %s")
        filters.append("r.guest_capacity <= 5")
        params.append(total_guests)
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

    checkin = session.get('checkin')
    checkout = session.get('checkout')

    if not checkin or not checkout:
        flash("Please select check-in and check-out dates first!")
        return redirect(url_for('index'))

    cursor.execute("SELECT * FROM hotels WHERE id=%s", (hotel_id,))
    hotel = cursor.fetchone()

    cursor.execute("""
        SELECT r.*, 
            (r.total_rooms - IFNULL((
                SELECT SUM(b.rooms_booked)
                FROM bookings b
                WHERE b.room_id = r.id
                AND NOT (b.checkout <= %s OR b.checkin >= %s)
            ), 0)) AS available_rooms_today
        FROM rooms r
        WHERE r.hotel_id = %s
    """, (checkin, checkout, hotel_id))
    rooms = cursor.fetchall()

    features = request.args.getlist("features")  
    conn.close()

    return render_template('hotel_detail.html', hotel=hotel, rooms=rooms, features=features)

@app.route('/book/<int:room_id>', methods=['GET', 'POST'])
def book_room(room_id):
    if 'user_id' not in session:
        session['next'] = url_for('book_room', room_id=room_id)
        return redirect(url_for('login'))

    conn = get_connection()
    cursor = conn.cursor()

    # ✅ Get hotel_id and total_rooms related to this room
    cursor.execute("SELECT hotel_id, total_rooms FROM rooms WHERE id = %s", (room_id,))
    room_info = cursor.fetchone()

    if not room_info:
        conn.close()
        flash("Room not found.")
        return redirect(url_for('index'))

    hotel_id = room_info[0]
    total_rooms = room_info[1]

    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        govt_id = request.form['govt_id']
        crib_request = bool(request.form.get('crib_request'))
        selected_features = request.form.getlist('features')
        features_string = ",".join(selected_features) if selected_features else "None"
        
        checkin = session.get('checkin')
        checkout = session.get('checkout')
        guest_count = session.get('guest_count', 1)
        rooms_requested = session.get('rooms', 1)

        try:
            checkin_date = datetime.strptime(checkin, "%Y-%m-%d")
            checkout_date = datetime.strptime(checkout, "%Y-%m-%d")
            if checkout_date <= checkin_date:
                conn.close()
                return "Error: Check-out date must be after check-in date.", 400
        except Exception:
            conn.close()
            return "Error: Invalid check-in/check-out format", 400

        cursor.execute("""
            SELECT SUM(rooms_booked) FROM bookings
            WHERE room_id = %s
            AND NOT (checkout <= %s OR checkin >= %s)
        """, (room_id, checkin, checkout))
        booked_rooms = cursor.fetchone()[0] or 0

        if (booked_rooms + rooms_requested) > total_rooms:
            conn.close()
            flash("❌ Sorry, this room is currently unavailable for booking on selected dates!")
            return redirect(url_for('hotel_detail', hotel_id=hotel_id))

        cursor.execute("""
        INSERT INTO bookings (room_id, name, email, phone, guest_count,govt_id, crib_request, checkin, checkout,user_id, rooms_booked, features)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (room_id, name, email, phone, guest_count,govt_id, crib_request, checkin, checkout,session['user_id'], rooms_requested, features_string))
        
        booking_id = cursor.lastrowid

        for i in range(1, int(guest_count)):
            co_name = request.form.get(f'co_name_{i}')
            co_age = request.form.get(f'co_age_{i}')
            if co_name and co_age:
                cursor.execute(
                    "INSERT INTO co_customers (booking_id, name, age) VALUES (%s, %s, %s)",
                    (booking_id, co_name, co_age)
                )

        conn.commit()
        conn.close()

        return redirect(url_for('invoice', booking_id=booking_id))

    features = request.args.getlist("features")
    conn.close()

    return render_template('book.html', room_id=room_id, features=features)


@app.route('/download_invoice/<int:booking_id>')
def download_invoice(booking_id):
    # (Re)fetch booking info (similar query as above)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT b.name, b.email, b.phone, b.guest_count,
               b.checkin, b.checkout, b.govt_id,
               r.price, h.name
        FROM bookings b
        JOIN rooms r ON b.room_id = r.id
        JOIN hotels h ON r.hotel_id = h.id
        WHERE b.id = %s
    """, (booking_id,))
    booking = cursor.fetchone()
    conn.close()

    if not booking:
        return abort(404, description="Booking not found")

    # Generate the PDF file (using fpdf or any library)
    pdf_path = generate_invoice_pdf(booking, booking_id)
    if not pdf_path or not os.path.exists(pdf_path):
        return "Error generating invoice PDF", 500

    # Send the PDF as attachment
    # The as_attachment flag forces a download prompt (Download).
    return send_file(pdf_path, as_attachment=True,
                     download_name=f"invoice_{booking_id}.pdf",
                     mimetype='application/pdf')


@app.route('/invoice/<int:booking_id>')
def invoice(booking_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT b.name, b.email, b.phone, b.guest_count,
                b.checkin, b.checkout, b.govt_id, b.features,
                r.price, h.name
        FROM bookings b
        JOIN rooms r ON b.room_id = r.id
        JOIN hotels h ON r.hotel_id = h.id
        WHERE b.id = %s
        """, (booking_id,))

    row = cursor.fetchone()
    conn.close()

    if not row:
        return "Booking not found", 404

    # unpack the row
    (name, email, phone, guests, checkin_str, checkout_str, govt_id, features, price_per_night, hotel_name) = row

    checkin_date = checkin_str
    checkout_date = checkout_str
    nights = (checkout_date - checkin_date).days
    if nights < 1:
        nights = 1

    room_total = price_per_night * nights
    meal_price_per_person_per_day = 1000
    meal_total = guests * meal_price_per_person_per_day * nights

    discount_percent = 0
    if nights > 7:
        discount_percent = 10
    elif nights > 3:
        discount_percent = 5

    discount_amount = (float(room_total) + float(meal_total)) * discount_percent / 100
    room_total = float(room_total)
    meal_total = float(meal_total)
    discount_amount = float(discount_amount)

    subtotal = room_total + meal_total - discount_amount
    gst = subtotal * 0.18
    grand_total = subtotal + gst

    booking = {
        'name': name,
        'email': email,
        'phone': phone,
        'guest_count': guests,
        'checkin': checkin_str,
        'checkout': checkout_str,
        'govt_id': govt_id,
        'features': features,  
        'hotel_name': hotel_name,
        'booking_id': booking_id
    }

    price = {
        'nights': nights,
        'price_per_night': float(price_per_night),
        'room_total': room_total,
        'meal_plan': 'Full-board',
        'meal_total': meal_total,
        'discount': discount_amount,
        'gst': gst,
        'grand_total': grand_total
    }

    return render_template('invoice.html', booking=booking, price=price)





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
        flash("Signup Successful! Please login.", "success")
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

            # ✅ Redirect to next page if available
            next_page = session.pop('next', None)
            if next_page:
                return redirect(next_page)
            else:
                return redirect(url_for('index'))

        flash("Invalid email or password!", "error")
        return redirect(url_for('login'))

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