# Building the health-sync Shortcut (Phase 2)

This iPhone Shortcut sends the last 3 days of Apple Health data to the backend every time you open Instagram. It takes about 20 minutes to build once. You build one block for HRV, then duplicate it for each other metric.

How it works:

- For each metric, the Shortcut finds the last 3 days of samples and turns each one into a line of text: `start|end|value|unit`.
- It sends all the metrics in one JSON request to `/ingest/health`, with your `INGEST_SECRET` in a header.
- The backend stores each sample once, so resending the same days is harmless, and rebuilds each day's numbers.
- The reply says how many samples arrived, and lists any lines it couldn't read.

You'll need:

- the backend URL: `https://agent-office-production-d0e3.up.railway.app/ingest/health`
- your `INGEST_SECRET` value from Railway (backend service → Variables). Type it into the Shortcut only.

> I couldn't test this on a real iPhone, and the Shortcuts app renames things between iOS versions. If an action or option has a slightly different name, pick the closest match. If the reply lists skipped lines, paste them into the Claude Code chat and the backend will be adjusted to accept them.

## 1. Create the Shortcut

Shortcuts app → **+** → name it **Health Sync**.

## 2. The HRV block (the template for every metric)

Add these actions in order:

1. **Find Health Samples**
   - Type: **Heart Rate Variability**
   - Add filter: **Start Date** · **is in the last** · **3 days**
   - Sort by: **Start Date**, Oldest First
   - Limit: off
2. **Repeat with Each** (input: *Health Samples* from step 1)
   1. **Format Date**: date = *Repeat Item → Start Date*. Format: **ISO 8601**, turn **Include ISO 8601 Time** on.
   2. **Format Date**: date = *Repeat Item → End Date*. Same settings.
   3. **Text**: build exactly this line, inserting the variables by tapping them:
      `Formatted Date (1)` `|` `Formatted Date (2)` `|` `Repeat Item → Value` `|` `Repeat Item → Unit`
      (the `|` is the vertical bar key, with no spaces around it)
3. *(End Repeat)*
4. **Combine Text**: input = *Repeat Results*, combine with **New Lines**.
5. Rename that *Combined Text* variable to **hrv**: long-press it → Rename. This makes the next steps easy to read.

## 3. Duplicate for the other metrics

Repeat steps 1–5 of the HRV block for each metric below, changing only the **Type** and the final variable name. Long-pressing an action → **Duplicate** copies it, which saves some tapping; rebuilding each block by hand works just as well.

| Health type in Shortcuts | Variable / JSON key | Notes |
| --- | --- | --- |
| Heart Rate Variability | `hrv` | done above |
| Resting Heart Rate | `resting_hr` | |
| Respiratory Rate | `respiratory_rate` | |
| Sleeping Wrist Temperature (may show as Wrist Temperature) | `wrist_temp` | °C or °F both work |
| VO2 Max (Cardio Fitness) | `vo2max` | |
| Running Ground Contact Time | `ground_contact` | |
| Running Vertical Oscillation | `vertical_oscillation` | |
| Running Stride Length | `stride_length` | |
| Active Energy | `active_energy` | In Find Health Samples set **Group By: Day**. Apple then sends one deduplicated total per day instead of thousands of small samples counted twice by iPhone and Watch |
| Sleep (Sleep Analysis) | `sleep` | The Value is the stage name (Core, Deep, REM, Awake, In Bed). Leave the Unit variable in; it's simply empty |

If a type isn't offered on your phone, skip it; every metric is optional.

## 4. Send it

1. **Get Contents of URL**
   - URL: `https://agent-office-production-d0e3.up.railway.app/ingest/health`
   - Show More → Method: **POST**
   - Headers: add `X-Ingest-Secret` = *your INGEST_SECRET*
   - Request Body: **JSON**. Add one **Text** field per metric: key = the JSON key from the table, value = that metric's combined-text variable (`hrv`, `resting_hr`, ...).
2. **Show Notification**: body = *Contents of URL*. Keep it while testing; remove it once things work if the pop-up gets annoying.

## 5. First run

Tap ▶. iOS asks for Health permission for each data type: allow all of them. It may also ask to allow sending data to the railway.app domain: choose **Always Allow**.

The notification should show something like:

```json
{"samples": 412, "days_updated": ["2026-10-06", "2026-10-07", "2026-10-08"], "skipped": [], "skipped_count": 0, "unknown_fields": []}
```

| You see | Meaning |
| --- | --- |
| `samples` above 0, `skipped_count` 0 | Working |
| `skipped` lines | Some lines weren't understood. Paste them into the Claude Code chat |
| `unknown_fields` | A JSON key is misspelled; compare with the table |
| `bad or missing X-Ingest-Secret` | The header name or value doesn't match Railway |
| `INGEST_SECRET is not set` | The variable is missing in Railway |

## 6. Run it automatically when you open Instagram

Shortcuts → **Automation** tab → **+** → **App** → choose **Instagram**, tick **Is Opened** → **Run Immediately** (not "Run After Confirmation") → Next → **Health Sync**.

Opening an app means the phone is unlocked, which is when iOS lets Shortcuts read Health data.

### Optional: only once a day

Running on every Instagram open is safe, because duplicates are ignored, but it sends data more often than needed. To limit it to once a day, add this at the very **top** of the Shortcut:

1. **Get File** from Shortcuts folder, path `health-sync-last.txt`. Turn off *Error If Not Found*.
2. **Format Date**: *Current Date*, format **Custom** `yyyy-MM-dd`.
3. **If** *File* **is** *Formatted Date* → **Stop This Shortcut**. **End If**.

And at the very **bottom**:

4. **Save File**: input = the *Formatted Date* from step 2, destination Shortcuts folder, path `health-sync-last.txt`, **Overwrite If File Exists** on.

Keep your phone passcode on: it's what keeps Health data encrypted, and the Instagram trigger doesn't need it removed.
