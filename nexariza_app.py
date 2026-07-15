import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
import smtplib
import ssl
import csv
import time
import threading
from email.message import EmailMessage

# --- CONFIGURATION ---
SMTP_SERVER = "smtp.zoho.com"   
SMTP_PORT = 465                 
SENDER_EMAIL = "contact@nexariza.com"  
SENDER_PASSWORD = "tJXHtsmf0QfU" 

class NexarizaApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Nexariza - Autonomous Mail Engine")
        self.root.geometry("650x700")
        self.root.configure(bg="#1e1e2e") 
        
        self.csv_path = ""
        self.is_sending = False

        # --- UI DESIGN ELEMENTS ---
        # Title
        title = tk.Label(root, text="NEXARIZA EMAIL ENGINE", font=("Helvetica", 16, "bold"), fg="#cdd6f4", bg="#1e1e2e")
        title.pack(pady=15)

        # File Selector Section (Fixed 'px' to 'padx')
        file_frame = tk.Frame(root, bg="#1e1e2e")
        file_frame.pack(fill="x", padx=20, pady=5)
        
        self.btn_browse = tk.Button(file_frame, text="Browse CSV File", command=self.browse_file, font=("Helvetica", 10, "bold"), bg="#89b4fa", fg="#11111b", bd=0, padx=15, pady=5)
        self.btn_browse.pack(side="left", padx=5)
        
        self.lbl_file = tk.Label(file_frame, text="No file selected", font=("Helvetica", 10), fg="#a6adc8", bg="#1e1e2e", wraplength=400, justify="left")
        self.lbl_file.pack(side="left", padx=10)

        # Subject Line Input (Fixed 'px' to 'padx')
        lbl_sub = tk.Label(root, text="Email Subject Line:", font=("Helvetica", 11, "bold"), fg="#cdd6f4", bg="#1e1e2e")
        lbl_sub.pack(anchor="w", padx=25, pady=(15, 2))
        
        self.ent_subject = tk.Entry(root, font=("Helvetica", 11), bg="#313244", fg="#cdd6f4", insertbackground="white", bd=1, relief="flat")
        self.ent_subject.pack(fill="x", padx=25, ipady=6)
        self.ent_subject.insert(0, "Operational bottleneck / Nexariza") 

        # Message Body Input (Fixed 'px' to 'padx')
        lbl_body = tk.Label(root, text="Email Body (Use {name} as a placeholder):", font=("Helvetica", 11, "bold"), fg="#cdd6f4", bg="#1e1e2e")
        lbl_body.pack(anchor="w", padx=25, pady=(15, 2))
        
        self.txt_body = scrolledtext.ScrolledText(root, font=("Helvetica", 10), bg="#313244", fg="#cdd6f4", insertbackground="white", bd=1, relief="flat", height=12)
        self.txt_body.pack(fill="both", padx=25, expand=True)
        
        default_body = """Hi {name},

I was looking over your operations and wanted to check who handles your workflow automation and system integrations.

We recently helped a group streamline their data pipelines, removing about 15 hours of manual engineering tasks per week. I wanted to see if reducing manual technical overhead is a priority for your team this quarter?

Regards,

Hassan Nadeem
Founder, Nexariza"""
        self.txt_body.insert(tk.END, default_body)

        # Execution Controls (Fixed 'px' to 'padx')
        self.btn_send = tk.Button(root, text="🚀 START CAMPAIGN", command=self.start_sending_thread, font=("Helvetica", 12, "bold"), bg="#a6e3a1", fg="#11111b", bd=0, pady=10)
        self.btn_send.pack(fill="x", padx=25, pady=15)

        # Live Logger Status Output (Fixed 'px' to 'padx')
        lbl_log = tk.Label(root, text="Execution Status Log:", font=("Helvetica", 10, "bold"), fg="#a6adc8", bg="#1e1e2e")
        lbl_log.pack(anchor="w", padx=25)
        
        self.txt_log = scrolledtext.ScrolledText(root, font=("Consolas", 9), bg="#11111b", fg="#a6e3a1", height=8, state="disabled")
        self.txt_log.pack(fill="x", padx=25, pady=(2, 20))

    # --- FUNCTIONALITY ENGINE ---
    def browse_file(self):
        file_selected = filedialog.askopenfilename(filetypes=[("CSV Files", "*.csv")])
        if file_selected:
            self.csv_path = file_selected
            self.lbl_file.config(text=file_selected)
            self.log_message(f"Loaded database path successfully.")

    def log_message(self, message):
        self.txt_log.config(state="normal")
        self.txt_log.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {message}\n")
        self.txt_log.see(tk.END)
        self.txt_log.config(state="disabled")

    def start_sending_thread(self):
        if not self.csv_path:
            messagebox.showerror("Error", "Please select your clients.csv file first.")
            return
        if self.is_sending:
            return
        
        threading.Thread(target=self.process_delivery, daemon=True).start()

    def process_delivery(self):
        self.is_sending = True
        self.btn_send.config(text="🛑 SENDING IN PROGRESS...", bg="#f38ba8", state="disabled")
        self.btn_browse.config(state="disabled")
        
        subject = self.ent_subject.get()
        body_template = self.txt_body.get("1.0", tk.END).strip()
        context = ssl.create_default_context()

        try:
            self.log_message("Connecting securely to Zoho SMTP cluster...")
            with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=context) as server:
                server.login(SENDER_EMAIL, SENDER_PASSWORD)
                self.log_message("Authentication verified. Parsing lead file rows...")
                
                with open(self.csv_path, mode="r", encoding="utf-8") as file:
                    reader = csv.DictReader(file)
                    
                    for row in reader:
                        name = row.get('Decision Maker Name') or row.get('name') or row.get('Name') or row.get('NAME') or "There"
                        recipient = row.get('Business Email') or row.get('email') or row.get('Email') or row.get('EMAIL')
                        
                        if not recipient:
                            continue

                        personalized_body = body_template.replace("{name}", name)

                        msg = EmailMessage()
                        msg['Subject'] = subject
                        msg['From'] = f"Hassan Nadeem <{SENDER_EMAIL}>"
                        msg['To'] = recipient
                        msg.set_content(personalized_body)

                        server.send_message(msg)
                        self.log_message(f"Dispatched successfully to {name} ({recipient})")
                        
                        self.log_message("Holding for 20 seconds anti-spam buffer...")
                        time.sleep(20)

                self.log_message("Campaign sequence finished running.")
                messagebox.showinfo("Success", "All personalized emails sent successfully!")

        except Exception as e:
            self.log_message(f"Fatal Interrupt: {e}")
            messagebox.showerror("Execution Error", str(e))
        
        self.is_sending = False
        self.btn_send.config(text="🚀 START CAMPAIGN", bg="#a6e3a1", state="normal")
        self.btn_browse.config(state="normal")

if __name__ == "__main__":
    root = tk.Tk()
    app = NexarizaApp(root)
    root.mainloop()