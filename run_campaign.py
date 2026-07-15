import httpx
import json
import time
import sys

# Fix Unicode printing issues on Windows terminals
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

API_URL = "http://127.0.0.1:8000"

def wait_for_campaign(client):
    print("Waiting for campaign to complete...", end="")
    while True:
        status_res = client.get(f"{API_URL}/campaign/status")
        status_res.raise_for_status()
        data = status_res.json()
        if data["status"] in ["completed", "failed", "cancelled"]:
            print()
            return data
        print(".", end="")
        sys.stdout.flush()
        time.sleep(2)

def run_campaign():
    print("🚀 Starting Nexariza AI Outreach Campaign...")
    print("--------------------------------------------------")
    print("Please make sure the FastAPI server is running (uvicorn main:app).")
    
    with httpx.Client(timeout=30.0) as client:
        # 1. Preview Mode (Dry Run)
        print("\n🧪 Running in PREVIEW mode (no actual emails will be sent yet).")
        try:
            # Note: API was updated to run as a background task. 
            response = client.post(
                f"{API_URL}/campaign/run",
                json={"csv_path": "clients.csv", "mode": "dry_run", "delay_seconds": 1}
            )
            response.raise_for_status()
            
            data = wait_for_campaign(client)
            
            print(f"✅ Preview Complete! Processed {data.get('total', 0)} clients.")
            
            # Show previews
            for result in data.get('results', []):
                print(f"\n--- Preview for {result.get('name', '')} ({result.get('email', '')}) ---")
                print(f"Status: {result.get('status', '')}")
                if result.get('status') == 'failed':
                    print(f"Error: {result.get('error', 'Unknown error')}")
                else:
                    print(f"Subject: {result.get('email_subject', '')}")
                    print(f"Body snippet: {str(result.get('email_body', ''))[:150]}...")
                    
        except Exception as e:
            print(f"❌ Failed to reach the API or run preview: {e}")
            return

        print("\n--------------------------------------------------")
        choice = input("Do you want to run the LIVE campaign and actually SEND emails? (yes/no): ")
        
        if choice.lower() in ['y', 'yes']:
            print("\n🔥 Starting LIVE campaign...")
            try:
                live_response = client.post(
                    f"{API_URL}/campaign/run",
                    json={"csv_path": "clients.csv", "mode": "live", "delay_seconds": 60}
                )
                live_response.raise_for_status()
                
                live_data = wait_for_campaign(client)
                
                print("\n🎉 Live Campaign Finished!")
                print(f"Total: {live_data.get('total', 0)} | Sent: {live_data.get('sent', 0)} | Failed: {live_data.get('failed', 0)} | Skipped: {live_data.get('skipped', 0)}")
                
            except Exception as e:
                 print(f"❌ Failed during live campaign: {e}")
        else:
            print("Campaign aborted. No emails were sent.")

if __name__ == "__main__":
    run_campaign()
