import smtplib
import ssl
import csv
import time
import dns.resolver
from email.message import EmailMessage

# --- DIRECT ZOHO CONFIGURATION ---
SMTP_SERVER = "smtp.zoho.com"   
SMTP_PORT = 465                 
SENDER_EMAIL = "contact@nexariza.com"  
SENDER_PASSWORD = "tJXHtsmf0QfU"       

def is_valid_email_domain(email):
    try:
        domain = email.split('@')[-1]
        answers = dns.resolver.resolve(domain, 'MX')
        for rdata in answers:
            if str(rdata.exchange).rstrip('.') == '':
                return False
        return True
    except Exception:
        return False

def send_important_outreach():
    context = ssl.create_default_context()

    try:
        print("Connecting to Zoho SMTP server...")
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=context) as server:
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            print("Successfully authenticated with Zoho Servers.")
            
            with open("clients.csv", mode="r", encoding="utf-8") as file:
                reader = csv.DictReader(file)
                
                for row in reader:
                    name = row.get('Decision Maker') or row.get('Decision Maker Name') or row.get('name') or row.get('Name') or "There"
                    recipient = row.get('Direct Email') or row.get('Corporate Email') or row.get('Business Email') or row.get('email') or row.get('Email') or ""

                    if not is_valid_email_domain(recipient):
                        print(f"Skipping {recipient} - Invalid email domain (No MX record).")
                        continue

                    msg = EmailMessage()
                    
                    # Direct, professional, non-spammy subject line
                    msg['Subject'] = f"Operational bottleneck / Nexariza AI"
                    msg['From'] = f"Ahmed Yasin@Nexariza <{SENDER_EMAIL}>"
                    msg['To'] = recipient

                    # Clean, direct, high-value plain text email body
                    text_content = f"""Hi {name},

I was looking over your operations and wanted to check who handles your workflow automation and system integrations.

We recently helped a group streamline their data pipelines, removing about 15 hours of manual engineering tasks per week. I wanted to see if reducing manual technical overhead is a priority for your team this quarter?

If you are the right person to speak with, let me know. If not, who would you recommend I connect with?

Regards,

Ahmed Yasin
Founder, Nexariza AI
{SENDER_EMAIL}
"""
                    msg.set_content(text_content)

                    # Send the mail
                    server.send_message(msg)
                    print(f"Successfully sent important mail to: {name} ({recipient})")
                    
                    # Safety delay to protect your domain reputation
                    print("Waiting 50 seconds...")
                    time.sleep(50)

            print("Campaign finished!")

    except Exception as e:
        print(f"Error occurred: {e}")

if __name__ == "__main__":
    send_important_outreach()