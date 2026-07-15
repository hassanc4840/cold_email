import smtplib
import ssl
import csv
import time
from email.message import EmailMessage

# --- CONFIGURATION ---
SMTP_SERVER = "smtp.gmail.com"  # Use smtp.office365.com for Outlook
SMTP_PORT = 465
SENDER_EMAIL = "chassan965@gmail.com"
SENDER_PASSWORD = "bazh rxwa xuxt dmjx" # Use an App Password, not your login password

def send_outreach():
    # Create a secure SSL context
    context = ssl.create_default_context()

    try:
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=context) as server:
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            
            with open("clients.csv", mode="r") as file:
                reader = csv.DictReader(file)
                for row in reader:
                    name = row.get('name', row.get('Name', 'Unknown'))
                    recipient = row.get('email', row.get('Email', ''))

                    # Create the email
                    msg = EmailMessage()
                    msg['Subject'] = f"Revolutionizing Your Workflow with Nexariza"
                    msg['From'] = SENDER_EMAIL
                    msg['To'] = recipient

                    # Professional Email Body
                    html_content = f"""
                    <html>
                        <body>
                            <p>Hello {name},</p>
                            <p>I’ve been following your work and thought you might be interested in how 
                            <strong>Nexariza</strong> is helping companies scale through intelligent automation.</p>
                            <p>We specialize in bespoke digital solutions that bridge the gap between 
                            complex technology and seamless user experiences.</p>
                            <p>Would you be open to a brief 5-minute chat next week to see if we can 
                            bring similar value to your team?</p>
                            <p>Best regards,<br>
                            <strong>Nexariza Team</strong></p>
                        </body>
                    </html>
                    """
                    msg.set_content("Please enable HTML to view this email.")
                    msg.add_alternative(html_content, subtype='html')

                    # Send and log
                    server.send_message(msg)
                    print(f"Success: Email sent to {name} ({recipient})")
                    
                    # Anti-spam delay (10 seconds between emails)
                    time.sleep(10)

    except Exception as e:
        print(f"Error: An error occurred: {e}")

if __name__ == "__main__":
    send_outreach()