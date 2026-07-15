import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
import smtplib
import ssl
import csv
import time
import threading
import json
import os
import dns.resolver
from datetime import datetime, timezone
from email.message import EmailMessage

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

CONFIG_FILE = "config.json"
HISTORY_FILE = "sent_history.json"
HISTORY_CSV_FILE = "sent_history.csv"


def _load_sent_history() -> dict:
    """Load sent history from JSON file."""
    default = {"sent_emails": {}, "processed_replies": [], "auto_replies": []}
    if not os.path.exists(HISTORY_FILE):
        return default
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            for key in default:
                if key not in data:
                    data[key] = default[key]
            return data
    except Exception:
        return default


def _save_sent_history(data: dict) -> None:
    """Save sent history to JSON file."""
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def is_already_contacted(email: str) -> bool:
    """Check if this email address was already contacted."""
    history = _load_sent_history()
    return email.strip().lower() in history["sent_emails"]


def register_sent(email: str, name: str, subject: str, body: str) -> None:
    """Record a sent email in both JSON and CSV history (keyed by email address)."""
    email_clean = email.strip().lower()
    sent_at = datetime.now(timezone.utc).isoformat()
    history = _load_sent_history()
    history["sent_emails"][email_clean] = {
        "name": name,
        "subject": subject,
        "body": body,
        "sent_at": sent_at
    }
    _save_sent_history(history)
    # Also append to CSV
    file_exists = os.path.isfile(HISTORY_CSV_FILE)
    try:
        with open(HISTORY_CSV_FILE, mode='a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["Email", "Name", "Subject", "Body", "Sent At"])
            writer.writerow([email_clean, name, subject, body, sent_at])
    except Exception:
        pass

class NexarizaEnhancedApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Nexariza - Advanced Mail Engine")
        self.root.geometry("800x850")
        self.root.configure(bg="#1e1e2e")
        
        self.csv_path = ""
        self.is_sending = False
        self.cancel_flag = False
        
        self.stats = {"total": 0, "sent": 0, "failed": 0}
        
        self.load_config()
        self.setup_ui()

    def load_config(self):
        self.config = {
            "smtp_server": "smtp.zoho.com",
            "smtp_port": "465",
            "sender_email": "contact@nexariza.com",
            "sender_password": "tJXHtsmf0QfU"
        }
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    self.config.update(json.load(f))
            except Exception:
                pass

    def save_config(self):
        with open(CONFIG_FILE, "w") as f:
            json.dump({
                "smtp_server": self.ent_server.get(),
                "smtp_port": self.ent_port.get(),
                "sender_email": self.ent_email.get(),
                "sender_password": self.ent_pass.get()
            }, f)
        messagebox.showinfo("Saved", "SMTP Configuration saved successfully!")

    def setup_ui(self):
        # Configure styles
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("TProgressbar", thickness=15, background="#a6e3a1", troughcolor="#313244")
        style.configure("TNotebook", background="#1e1e2e", borderwidth=0)
        style.configure("TNotebook.Tab", background="#313244", foreground="#cdd6f4", padding=[10, 5], font=("Helvetica", 10, "bold"))
        style.map("TNotebook.Tab", background=[("selected", "#89b4fa")], foreground=[("selected", "#11111b")])
        
        # Title
        title_frame = tk.Frame(self.root, bg="#1e1e2e")
        title_frame.pack(fill="x", pady=15)
        tk.Label(title_frame, text="NEXARIZA ADVANCED EMAIL ENGINE", font=("Helvetica", 18, "bold"), fg="#89b4fa", bg="#1e1e2e").pack()
        tk.Label(title_frame, text="Automated Outreach Pipeline", font=("Helvetica", 10), fg="#a6adc8", bg="#1e1e2e").pack()

        # Tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=20, pady=5)
        
        self.tab_campaign = tk.Frame(self.notebook, bg="#1e1e2e")
        self.tab_settings = tk.Frame(self.notebook, bg="#1e1e2e")
        
        self.notebook.add(self.tab_campaign, text="Campaign Manager")
        self.notebook.add(self.tab_settings, text="SMTP Settings")
        
        self.setup_settings_tab()
        self.setup_campaign_tab()

    def setup_settings_tab(self):
        frame = tk.Frame(self.tab_settings, bg="#1e1e2e")
        frame.pack(padx=30, pady=30, fill="x")
        
        labels = ["SMTP Server:", "SMTP Port:", "Sender Email:", "App Password:"]
        self.ent_server = self.create_setting_row(frame, labels[0], self.config["smtp_server"], 0)
        self.ent_port = self.create_setting_row(frame, labels[1], self.config["smtp_port"], 1)
        self.ent_email = self.create_setting_row(frame, labels[2], self.config["sender_email"], 2)
        self.ent_pass = self.create_setting_row(frame, labels[3], self.config["sender_password"], 3, show="*")
        
        btn_save = tk.Button(self.tab_settings, text="💾 Save Configuration", command=self.save_config, font=("Helvetica", 11, "bold"), bg="#89b4fa", fg="#11111b", bd=0, padx=20, pady=8)
        btn_save.pack(pady=20)

    def create_setting_row(self, parent, label_text, default_val, row, show=None):
        tk.Label(parent, text=label_text, font=("Helvetica", 11, "bold"), fg="#cdd6f4", bg="#1e1e2e").grid(row=row, column=0, sticky="w", pady=10)
        ent = tk.Entry(parent, font=("Helvetica", 11), bg="#313244", fg="#cdd6f4", insertbackground="white", bd=1, relief="flat", show=show)
        ent.grid(row=row, column=1, sticky="ew", padx=15, ipady=5)
        ent.insert(0, default_val)
        parent.columnconfigure(1, weight=1)
        return ent

    def setup_campaign_tab(self):
        # File Selector
        file_frame = tk.Frame(self.tab_campaign, bg="#1e1e2e")
        file_frame.pack(fill="x", pady=15)
        
        self.btn_browse = tk.Button(file_frame, text="📁 Browse Database (CSV)", command=self.browse_file, font=("Helvetica", 10, "bold"), bg="#89b4fa", fg="#11111b", bd=0, padx=15, pady=6)
        self.btn_browse.pack(side="left", padx=5)
        
        self.lbl_file = tk.Label(file_frame, text="No database connected", font=("Helvetica", 10, "italic"), fg="#f38ba8", bg="#1e1e2e")
        self.lbl_file.pack(side="left", padx=10)

        # Subject Line
        tk.Label(self.tab_campaign, text="Email Subject:", font=("Helvetica", 11, "bold"), fg="#cdd6f4", bg="#1e1e2e").pack(anchor="w", pady=(10, 2))
        self.ent_subject = tk.Entry(self.tab_campaign, font=("Helvetica", 11), bg="#313244", fg="#cdd6f4", insertbackground="white", bd=1, relief="flat")
        self.ent_subject.pack(fill="x", ipady=6)
        self.ent_subject.insert(0, "Operational bottleneck / Nexariza") 

        # Message Body
        tk.Label(self.tab_campaign, text="Email Body (Placeholders: {name}, {company}):", font=("Helvetica", 11, "bold"), fg="#cdd6f4", bg="#1e1e2e").pack(anchor="w", pady=(15, 2))
        self.txt_body = scrolledtext.ScrolledText(self.tab_campaign, font=("Helvetica", 10), bg="#313244", fg="#cdd6f4", insertbackground="white", bd=1, relief="flat", height=10)
        self.txt_body.pack(fill="both", expand=True)
        self.txt_body.insert(tk.END, "Hi {name},\n\nI was looking over your operations and wanted to check who handles your workflow automation.\n\nRegards,\nHassan Nadeem")

        # Options
        options_frame = tk.Frame(self.tab_campaign, bg="#1e1e2e")
        options_frame.pack(fill="x", pady=10)
        self.var_dry_run = tk.BooleanVar(value=False)
        self.var_html = tk.BooleanVar(value=False)
        
        tk.Checkbutton(options_frame, text="🧪 Dry Run (Test without sending)", variable=self.var_dry_run, bg="#1e1e2e", fg="#cdd6f4", selectcolor="#313244", activebackground="#1e1e2e", activeforeground="#cdd6f4", font=("Helvetica", 10)).pack(side="left", padx=10)
        tk.Checkbutton(options_frame, text="🌐 Send as HTML", variable=self.var_html, bg="#1e1e2e", fg="#cdd6f4", selectcolor="#313244", activebackground="#1e1e2e", activeforeground="#cdd6f4", font=("Helvetica", 10)).pack(side="left", padx=10)

        # Progress and Stats
        self.progress_var = tk.DoubleVar()
        self.progress = ttk.Progressbar(self.tab_campaign, style="TProgressbar", orient="horizontal", mode="determinate", variable=self.progress_var)
        self.progress.pack(fill="x", pady=10)
        
        stats_frame = tk.Frame(self.tab_campaign, bg="#1e1e2e")
        stats_frame.pack(fill="x", pady=5)
        
        self.lbl_stats = tk.Label(stats_frame, text="Ready | Sent: 0 | Failed: 0 | Total: 0", font=("Helvetica", 10, "bold"), fg="#a6adc8", bg="#1e1e2e")
        self.lbl_stats.pack()

        # Controls
        ctrl_frame = tk.Frame(self.tab_campaign, bg="#1e1e2e")
        ctrl_frame.pack(fill="x", pady=10)
        
        self.btn_send = tk.Button(ctrl_frame, text="🚀 START CAMPAIGN", command=self.start_sending_thread, font=("Helvetica", 12, "bold"), bg="#a6e3a1", fg="#11111b", bd=0, pady=10)
        self.btn_send.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        self.btn_cancel = tk.Button(ctrl_frame, text="🛑 CANCEL", command=self.cancel_campaign, font=("Helvetica", 12, "bold"), bg="#f38ba8", fg="#11111b", bd=0, pady=10, state="disabled")
        self.btn_cancel.pack(side="right", fill="x", expand=True, padx=(5, 0))

        # Log
        self.txt_log = scrolledtext.ScrolledText(self.tab_campaign, font=("Consolas", 9), bg="#11111b", fg="#a6adc8", height=8, state="disabled")
        self.txt_log.pack(fill="both", expand=True, pady=(5, 0))
        
        # Setup tags for colored logging
        self.txt_log.tag_config('success', foreground='#a6e3a1')
        self.txt_log.tag_config('error', foreground='#f38ba8')
        self.txt_log.tag_config('info', foreground='#89b4fa')
        self.txt_log.tag_config('warning', foreground='#f9e2af')

    def browse_file(self):
        file_selected = filedialog.askopenfilename(filetypes=[("CSV Files", "*.csv")])
        if file_selected:
            self.csv_path = file_selected
            self.lbl_file.config(text=os.path.basename(file_selected), fg="#a6e3a1")
            self.log_message(f"Database loaded: {self.csv_path}", "info")

    def log_message(self, message, level="info"):
        self.root.after(0, self._sync_log, message, level)

    def _sync_log(self, message, level):
        self.txt_log.config(state="normal")
        timestamp = time.strftime('%H:%M:%S')
        self.txt_log.insert(tk.END, f"[{timestamp}] ", "info")
        self.txt_log.insert(tk.END, f"{message}\n", level)
        self.txt_log.see(tk.END)
        self.txt_log.config(state="disabled")

    def update_stats(self):
        self.root.after(0, self._sync_stats)
        
    def _sync_stats(self):
        self.lbl_stats.config(text=f"Sent: {self.stats['sent']} | Failed: {self.stats['failed']} | Total: {self.stats['total']}")
        if self.stats['total'] > 0:
            self.progress_var.set((self.stats['sent'] + self.stats['failed']) / self.stats['total'] * 100)

    def cancel_campaign(self):
        if self.is_sending:
            self.cancel_flag = True
            self.log_message("Cancel requested. Waiting for current operation to finish...", "warning")
            self.btn_cancel.config(state="disabled")

    def start_sending_thread(self):
        if not self.csv_path:
            messagebox.showerror("Error", "Please select a database (CSV) file first.")
            return
        if self.is_sending:
            return
            
        self.is_sending = True
        self.cancel_flag = False
        self.stats = {"total": 0, "sent": 0, "failed": 0}
        self.progress_var.set(0)
        self.update_stats()
        
        self.btn_send.config(text="⏳ RUNNING...", bg="#f9e2af", state="disabled")
        self.btn_cancel.config(state="normal")
        self.btn_browse.config(state="disabled")
        
        threading.Thread(target=self.process_delivery, daemon=True).start()

    def process_delivery(self):
        subject = self.ent_subject.get()
        body_template = self.txt_body.get("1.0", tk.END).strip()
        is_html = self.var_html.get()
        is_dry_run = self.var_dry_run.get()
        
        server_addr = self.ent_server.get()
        port = int(self.ent_port.get())
        sender = self.ent_email.get()
        password = self.ent_pass.get()
        
        context = ssl.create_default_context()
        server = None
        
        try:
            # Read CSV to get total count
            with open(self.csv_path, mode="r", encoding="utf-8") as file:
                rows = list(csv.DictReader(file))
                self.stats["total"] = len(rows)
                self.update_stats()
                
            if self.stats["total"] == 0:
                self.log_message("No records found in CSV.", "warning")
                self._reset_ui()
                return

            if not is_dry_run:
                self.log_message(f"Connecting to SMTP: {server_addr}:{port}...", "info")
                server = smtplib.SMTP_SSL(server_addr, port, context=context)
                server.login(sender, password)
                self.log_message("Authentication verified.", "success")
            else:
                self.log_message("DRY RUN ACTIVATED - No actual emails will be sent.", "warning")
            
            for index, row in enumerate(rows):
                if self.cancel_flag:
                    self.log_message("Campaign aborted by user.", "error")
                    break
                    
                name = row.get('Decision Maker') or row.get('Decision Maker Name') or row.get('name') or row.get('Name') or row.get('NAME') or 'There'
                company = row.get('Company Name') or row.get('company') or row.get('Company') or row.get('COMPANY') or 'your company'
                recipient = row.get('Direct Email') or row.get('Corporate Email') or row.get('Business Email') or row.get('email') or row.get('Email') or row.get('EMAIL') or ''
                
                if not recipient:
                    self.log_message(f"Row {index+1}: Missing email, skipping.", "warning")
                    self.stats["failed"] += 1
                    self.update_stats()
                    continue

                # ── Duplicate check by EMAIL ADDRESS ──────────────────────────
                if is_already_contacted(recipient):
                    self.log_message(f"Row {index+1}: Already contacted {recipient}, skipping.", "warning")
                    self.stats["failed"] += 1
                    self.update_stats()
                    continue

                if not is_dry_run and not is_valid_email_domain(recipient):
                    self.log_message(f"Row {index+1}: Invalid email domain (No MX record) for {recipient}, skipping.", "error")
                    self.stats["failed"] += 1
                    self.update_stats()
                    continue

                try:
                    personalized_body = body_template.replace("{name}", name).replace("{company}", company)
                    
                    msg = EmailMessage()
                    msg['Subject'] = subject
                    msg['From'] = f"Nexariza Outreach <{sender}>"
                    msg['To'] = recipient
                    
                    if is_html:
                        msg.set_content("Please enable HTML to view this email.")
                        msg.add_alternative(personalized_body, subtype='html')
                    else:
                        msg.set_content(personalized_body)

                    if not is_dry_run:
                        # server.send_message(msg)
                        self.log_message(f"Email sending is disabled. Simulated send to {recipient}", "warning")
                        # Save to sent history so we never email this address again
                        register_sent(recipient, name, subject, personalized_body)
                        
                    self.stats["sent"] += 1
                    self.log_message(f"[{index+1}/{self.stats['total']}] Dispatched to {name} ({recipient})", "success")
                    
                    # Anti-spam delay only if not dry run and not the last email
                    if not is_dry_run and index < self.stats['total'] - 1 and not self.cancel_flag:
                        self.log_message("Anti-spam hold (50s)...", "info")
                        time.sleep(50)
                        
                except Exception as e:
                    self.stats["failed"] += 1
                    self.log_message(f"Failed to send to {recipient}: {str(e)}", "error")
                    
                self.update_stats()

            if not self.cancel_flag:
                self.log_message("Campaign sequence finished.", "success")
                self.root.after(0, lambda: messagebox.showinfo("Complete", "Campaign execution completed!"))

        except smtplib.SMTPAuthenticationError:
            self.log_message("Authentication failed! Check your email and app password.", "error")
            self.root.after(0, lambda: messagebox.showerror("Auth Error", "SMTP Authentication failed. Check Settings tab."))
        except Exception as e:
            self.log_message(f"Fatal Interrupt: {e}", "error")
            self.root.after(0, lambda: messagebox.showerror("Execution Error", str(e)))
        finally:
            if server is not None:
                try:
                    server.quit()
                except:
                    pass
            self._reset_ui()

    def _reset_ui(self):
        self.is_sending = False
        self.root.after(0, self._sync_reset_ui)
        
    def _sync_reset_ui(self):
        self.btn_send.config(text="🚀 START CAMPAIGN", bg="#a6e3a1", state="normal")
        self.btn_cancel.config(state="disabled")
        self.btn_browse.config(state="normal")

if __name__ == "__main__":
    root = tk.Tk()
    app = NexarizaEnhancedApp(root)
    root.mainloop()
