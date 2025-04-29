from fpdf import FPDF
import os

def generate_invoice_pdf(booking, booking_id):
    try:
        # Create PDF object
        pdf = FPDF()
        pdf.add_page()


        pdf.set_font("Arial", size=12)
        pdf.cell(200, 10, txt="Hotel Booking Invoice", ln=True, align="C",)

        pdf.ln(10)
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Arial", size=12)
        pdf.cell(200, 10, txt=f"Room No: {booking_id}", ln=True)
        pdf.cell(200, 10, txt=f"Customer: {booking[6]}", ln=True)  # booking[1] = name
        pdf.cell(200, 10, txt=f"Hotel: {booking[8]}", ln=True)  # booking[6] = hotel name
        pdf.cell(200, 10, txt=f"Email: {booking[1]}", ln=True)
        pdf.cell(200, 10, txt=f"Phone: {booking[2]}", ln=True)
        pdf.cell(200, 10, txt=f"Guests: {booking[3]}", ln=True)
        pdf.cell(200, 10, txt=f"Check-in: {booking[5]}", ln=True)  # booking[3] = checkin
        pdf.cell(200, 10, txt=f"Check-out: {booking[4]}", ln=True)  # booking[4] = checkout
        pdf.ln(10)
        pdf.ln(10)
        pdf.cell(200, 10, txt=f"Total Price: ${booking[7]}", ln=True)  # booking[5] = price

        # Save the PDF to a file
        pdf_dir = "invoices"
        if not os.path.exists(pdf_dir):
            os.makedirs(pdf_dir)

        pdf_path = os.path.join(pdf_dir, f"invoice_{booking_id}.pdf")
        pdf.output(pdf_path)

        # Check if the PDF file is created successfully
        if not os.path.exists(pdf_path):
            print(f"Error: Failed to create PDF file at {pdf_path}")
            return None

        return pdf_path

    except Exception as e:
        print(f"Error in generating PDF for booking ID {booking_id}: {e}")
        return None



