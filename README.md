# Inventory Dashboard — Setup Guide
## For Windows · Python · Streamlit · Gmail

---

## Step 1 — Copy your data files

Place your two daily CSV files inside the `data/` folder:

```
inventory_dashboard/
  data/
    All_facility_Shelfwise_Inventory_XXXXXX.csv   ← shelf-wise report
    FG_INVENTORY_REPORT_XXXXXX.csv                ← FG/DRR report
```

The app will automatically pick the most recently modified file
for each type, so you can just drop new files in each day.

---

## Step 2 — Install Python packages

Open Command Prompt (press Windows key, type `cmd`, press Enter).

Navigate to your project folder:
```
cd C:\path\to\inventory_dashboard
```

Install required packages:
```
pip install -r requirements.txt
```

---

## Step 3 — Run the dashboard

In the same Command Prompt window:
```
streamlit run Home.py
```

Your browser will open automatically at http://localhost:8501

---

## Step 4 — Set up Gmail auto-fetch (optional)

1. Enable IMAP in your Gmail:
   - Gmail → Settings (gear icon) → See all settings
   - Forwarding and POP/IMAP tab → Enable IMAP

2. Create a Gmail App Password:
   - Go to https://myaccount.google.com/security
   - Under "2-Step Verification" → App passwords
   - Select "Mail" and "Windows Computer"
   - Copy the 16-character password

3. Create a `.env` file in the `inventory_dashboard/` folder:
   ```
   GMAIL_USER=your_email@gmail.com
   GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
   ```

4. Edit the subject keywords in `data/email_ingestor.py`:
   - Change `subject_keyword` to match the actual subject lines
     of your two report emails

5. Test it manually:
   ```
   python data/email_ingestor.py
   ```

6. Schedule it via Windows Task Scheduler to run at 6 AM daily
   (instructions inside email_ingestor.py)

---

## Dashboard Pages

| Page                  | URL path              | What it shows                          |
|-----------------------|-----------------------|----------------------------------------|
| Home                  | /                     | Warehouse DOI vs PAN India DRR         |
| Inventory Health      | /Inventory_Health     | DOI & DRR per facility & SKU           |
| Aging & FEFO          | /Aging_FEFO           | Expiry risk + FEFO batch compliance    |
| Slow Moving           | /Slow_Moving          | Dead stock & slow-moving analysis      |
| Replenishment         | /Replenishment        | Auto-generated reorder suggestions     |

---

## Key Logic

**Warehouse DOI:**
```
PAN India DRR  = Sum of last 30 days sales across all B2C depots ÷ 30
Warehouse DOI  = Stock in (SL Ambient + SL Mother Hub) ÷ PAN India DRR
```

**DOI Status:**
- 🔴 Critical     → ≤ 7 days
- 🟡 At Risk      → 8–14 days
- 🟢 Healthy      → 15–30 days
- 🔵 Overstocked  → > 30 days
- ⚫ No Sales Data → DRR = 0

---

## Troubleshooting

**"No CSV found" error:**
Make sure your files are in the `data/` folder and their names
start with the correct prefix.

**Charts not loading:**
Run `pip install -r requirements.txt` again.

**Gmail fetch not working:**
Check that IMAP is enabled and App Password is correct in `.env`.
"# inventory_dashboard" 
