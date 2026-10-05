#!/usr/bin/env python3
"""Writes tasks.json. The expected answers are computed by the small reference solvers below, so every task is
deterministic and solvable. Edit the INPUTS, rerun, and the checker data follows. The prompts never state the house
rules: the student has to get them from the skill. Three families, six tasks each, two per split per family."""
import json, re, pathlib

# ---- family 1: invoice note -> JSON record ------------------------------------------------------
# House rules: id is "INV-" plus the number padded to 6 digits; customer in Title Case; date as YYYY-MM-DD;
# total in whole pence, and when the note says "+ VAT" add 20% (when it says "inc VAT" or nothing, do not).
INV_PROMPT = ("Turn this pasted invoice note into our record. Reply with a JSON object with exactly the keys "
              "id, customer, date, total_pence, and nothing else.\n\nNote: {note}")
INVOICES = [  # (note, number, customer, date, pence, plus_vat)
    ("inv no. 42 - acme widgets ltd - 3rd march 2026 - £1,200.50 + VAT", 42, "Acme Widgets Ltd", "2026-03-03", 120050, True),
    ("Invoice #7 for BRIGHT SPARK ELECTRICAL, dated 12/04/2026 (day first), amount £85 inc VAT", 7, "Bright Spark Electrical", "2026-04-12", 8500, False),
    ("ref 1031: harbour & co. billed on 9 Jan 26, total 2,300 GBP + VAT", 1031, "Harbour & Co.", "2026-01-09", 230000, True),
    ("INV-88 // oak street bakery // 28-Feb-2026 // £14.99", 88, "Oak Street Bakery", "2026-02-28", 1499, False),
    ("number 5120, delta freight limited, 1 June 2026, £10,000 + VAT", 5120, "Delta Freight Limited", "2026-06-01", 1000000, True),
    ("invoice 19 - northern lights design - 15/07/26 - £640.40 + VAT", 19, "Northern Lights Design", "2026-07-15", 64040, True),
]
def inv_expected(number, customer, date, pence, vat):
    return {"id": f"INV-{number:06d}", "customer": customer, "date": date, "total_pence": pence * 12 // 10 if vat else pence}

# ---- family 2: rewrite a note in house format ---------------------------------------------------
# House rules: dates as "05 Mar 2026" (two-digit day, three-letter month, no comma), money as "GBP 1,200.50"
# (code first, thousands comma, always two decimals), times in 24 hour "14:30".
FMT_PROMPT = "Rewrite this note in our house style. Reply with the rewritten note only.\n\nNote: {note}"
NOTES = [  # (input, expected)
    ("Meeting moved to March 5th, 2026 at 2:30pm. Budget is £1200.", "Meeting moved to 05 Mar 2026 at 14:30. Budget is GBP 1,200.00."),
    ("Deadline is 3 November 2026 at 9am. Late fee is £250.", "Deadline is 03 Nov 2026 at 09:00. Late fee is GBP 250.00."),
    ("Kick-off on 21 Jan 2027, 10:15am. The deposit is £3,450.5 and the balance is £12,000.", "Kick-off on 21 Jan 2027, 10:15. The deposit is GBP 3,450.50 and the balance is GBP 12,000.00."),
    ("Invoice paid on September 9, 2026 at 4pm. Amount: 75 pounds.", "Invoice paid on 09 Sep 2026 at 16:00. Amount: GBP 75.00."),
    ("Delivery on 15th December 2026 between 8am and 11:30am. Cost 1999.9 GBP.", "Delivery on 15 Dec 2026 between 08:00 and 11:30. Cost GBP 1,999.90."),
    ("Review set for 2 April 2027 at 12:05pm. Fee is £60 and the travel cap is £1,000.", "Review set for 02 Apr 2027 at 12:05. Fee is GBP 60.00 and the travel cap is GBP 1,000.00."),
]

# ---- family 3: document filename ----------------------------------------------------------------
# House rules: YYYYMMDD_slug_vNN_<first initial + surname, lowercase, no punctuation>.ext  where the slug is lowercase
# words joined by hyphens, with the words the/a/an/of/and/for and all punctuation removed; the extension is lowercase.
FILE_PROMPT = ("Give the filename for this document under our naming convention. Reply with the filename only.\n\n"
               "Title: {title}\nDate: {date}\nVersion: {version}\nAuthor: {author}\nFormat: {fmt}")
MONTHS = {m: i + 1 for i, m in enumerate("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split())}
FILES = [  # (title, date text, version, author, format)
    ("The Quarterly Sales Report", "5 March 2026", 3, "Jane Smith", "PDF"),
    ("Plan for Office Move and Budget", "21 November 2025", 12, "Omar Haddad", "DOCX"),
    ("Customer Survey Results (Final)", "1 February 2026", 2, "Priya Nair", "XLSX"),
    ("Q3 Marketing Plan: An Overview", "30 September 2026", 1, "Tom O'Neill", "PDF"),
    ("Vendor Contract for the Leeds Site", "14 August 2026", 4, "Sam Greene", "PDF"),
    ("Onboarding Checklist & FAQ", "9 January 2026", 10, "Li Wei", "DOCX"),
]
def file_expected(title, date, version, author, fmt):
    d, m, y = date.split(); stamp = f"{int(y):04d}{MONTHS[m[:3]]:02d}{int(d):02d}"
    words = [w for w in re.sub(r"[^a-z0-9 ]", "", title.lower().replace("&", " ")).split() if w not in {"the", "a", "an", "of", "and", "for"}]
    first, *rest = author.split(); who = re.sub(r"[^a-z]", "", (first[0] + rest[-1]).lower())
    return f"{stamp}_{'-'.join(words)}_v{version:02d}_{who}.{fmt.lower()}"

SPLITS = ["train", "train", "sel", "sel", "test", "test"]  # tasks 1-2 train, 3-4 selection, 5-6 test
tasks = []
for i, (note, n, cust, date, pence, vat) in enumerate(INVOICES):
    tasks.append(dict(id=f"inv{i+1}", split=SPLITS[i], family="invoice-json", kind="json",
                      prompt=INV_PROMPT.format(note=note), expected=inv_expected(n, cust, date, pence, vat)))
for i, (note, exp) in enumerate(NOTES):
    tasks.append(dict(id=f"fmt{i+1}", split=SPLITS[i], family="house-format", kind="exact", prompt=FMT_PROMPT.format(note=note), expected=exp))
for i, (title, date, version, author, fmt) in enumerate(FILES):
    tasks.append(dict(id=f"file{i+1}", split=SPLITS[i], family="filename", kind="exact",
                      prompt=FILE_PROMPT.format(title=title, date=date, version=version, author=author, fmt=fmt),
                      expected=file_expected(title, date, version, author, fmt)))
pathlib.Path(__file__).with_name("tasks.json").write_text(json.dumps(tasks, indent=1, ensure_ascii=False) + "\n")
for t in tasks: print(t["id"], t["split"], t["expected"])
