# Prototype guide: install, run a session, export

The prototype (`prototype/`) is the on-device usability test from proposal §4.3–4.5. It contains:
- a researcher setup screen with the 3×3 Latin square;
- one practice task, the same for everyone;
- the timed tasks, with automatic event logging;
- a Single Ease Question (SEQ) rating after each task;
- an export that the analysis pipeline reads directly.

It is a web app that you **install once from GitHub Pages**. After that it runs fully offline on the study
phone. Logs stay on the phone until you export them.

Screen recording is done separately with the phone's own recorder or a third-party app. The prototype does not record the screen.

> **Build status:** the mega-menu (MM) is built. Deep hierarchical (DH) and nested dropdown (ND) are TODO
> (see `prototype/PATTERN_API.md`). Until they are built, setup marks sessions as **test-only**, and DH/ND
> blocks show a *Skip block* button.

---

## 1. One-time GitHub setup (one team member, on a computer)

1. The repo must be **public** for free GitHub Pages. For a private repo, you need GitHub Pro, which is free with the GitHub Student Developer Pack.
   Only the app goes online. Participant data never does.
2. On GitHub, open **Settings → Pages → Build and deployment → Source** and choose **GitHub Actions**.
3. Merge the prototype into `main`. The **Deploy prototype** workflow (`.github/workflows/pages.yml`) runs
   on every push to `main` that changes `prototype/`. To run it by hand, open **Actions → Deploy prototype → Run workflow**.
4. When the workflow finishes, the app is at **`https://nomjie33.github.io/HCI2000-pipeline/`**. The same link is shown on the
   workflow run and under Settings → Pages.

## 2. Install on the study phone

The phone needs internet **only for this step**.

### Android (Chrome)
1. Open the link above in **Chrome**.
2. Wait until the home screen ("Navigation Study") appears, then tap **⋮ → Add to Home screen → Install**.
   On some phones this is called **Install app**.
3. Open the app from the new **Nav Study** icon. It opens full screen, without the browser bar.

### iPhone (Safari)
1. Open the link in **Safari**. Other iOS browsers cannot install web apps on older iOS versions.
2. Tap **Share → Add to Home Screen → Add**.
3. Always run the study **and export from the home-screen icon**. On iPhone, the installed app keeps its
   data separately from Safari, so sessions run in Safari do not appear in the app, and the reverse.

### Check that it works offline
1. Turn on **Airplane mode**.
2. Close the app fully (swipe it away) and open it again from the icon.
3. The home screen should load. If it does not, turn the internet back on, open the app once, wait 10 seconds, and try again.

### First-time device setup
1. Tap **Researcher** and enter the default PIN **2000**. The default is set in `prototype/data/study.json`.
2. Tap **Change PIN** and choose a new PIN for this phone. The new PIN is stored on the phone only.
   - The PIN only keeps participants out of setup and export. It is **not** a security control: the repo and the
     default PIN are public.
   - If you forget it, tap **Forgot PIN?**, type `RESET`, and the PIN goes back to the study.json default. No data is deleted.
3. Run one test session from start to finish, export it, then **Delete** it in the researcher area.
4. Phone settings for every session (proposal §4.4):
   - Do Not Disturb on.
   - Same brightness every time.
   - Auto-rotate off (portrait).
   - Battery saver off.
   - Screen recorder ready.

## 3. Running a session

This replaces Appendix C.1. You set the session up **once per participant**, not once per task.

1. Start the screen recording.
2. Open the app, tap **Researcher**, enter the PIN, then tap **New session**.
3. **Participant ID**: the app suggests the next one (`P01`, `P02`, …). IDs must be unique on the phone.
4. **Sequence**: the app suggests the next one in rotation (S1 → S2 → S3 → S1 …). You can override it.
   The **Latin square (Table 3)** is shown with the chosen row highlighted.
5. **Task order within each pair**: alternates between consecutive participants in the same sequence (§4.4).
   The app suggests the order from the sessions already stored on the phone.
6. Check the participant's task list (block, pattern, task, target), then tap **Start session**.
7. Hand the phone over. From here the participant moves through the screens alone:
   - The briefing (C.2 text) is shown on screen. You may also read it aloud.
   - **Practice task**: one task on a flat A–Z library page list. It uses none of the three experimental menus and is
     **not recorded**.
   - **Three blocks**, each opening with a "Menu style N of 3" screen and a break offer. Each block has two tasks, and each task runs like this:
     1. The scenario is shown, and the participant taps **Start**. The timer starts here.
     2. The participant navigates. **Give up** is always visible, and the task ends automatically at 180 s.
     3. The completion screen appears.
     4. The participant gives the **SEQ rating** (1 very difficult … 7 very easy).
   - End screen: "Please hand the phone back."
8. Take the phone back, then do the Google Form parts: demographics before the session, and the preference ranking
   and comments after it.
9. **Export right away** (section 4).

**During a task, you must not help** (C.5). If the app or phone fails during a task:
1. Long-press the **top-right corner of the screen for 3 seconds**, then enter the PIN.
2. Choose **Abort and re-run this task**. The broken attempt is set aside in `interrupted_trials.csv`, and the task
   starts again from the beginning with the same trial ID.
3. If the app was closed or reloaded mid-task, it shows **Task interrupted** next time. Enter the PIN to re-run the task.

Afterwards, if the screen recording confirms a fault, add the trial to `exclusions.csv` (§4.7).

The system Back gesture is disabled during the study. Only the website's own menu, Back and logo work.

## 4. Exporting

1. Open **Researcher → Export** next to the participant, or **Export all sessions**.
2. On phones with a share sheet, choose **Drive** and upload to the team folder. Otherwise the ZIP is
   saved to Downloads.
3. Do this **after every session**. Phone storage can be cleared by the OS, so the export is your backup.

The ZIP (`hci2000_export_<P01|all>_<date>.zip`) is a pipeline dataset folder:

| File | Contents |
| :-- | :-- |
| `events.csv` | one row per tap or navigation action, with `t_ms` since Start and a computed `on_path` flag (App. B). |
| `ratings.csv` | SEQ rating per trial. |
| `participants.csv` | `participant_id` and `sequence` filled in. **Copy the other columns in from the Google Form.** |
| `exclusions.csv` | header only. Add `trial_id,reason` rows for confirmed device/app faults. |
| `reference/tree.csv`, `reference/tasks.csv` | the exact tree and targets the phone used. |
| `session_info.csv` | audit file, not read by the pipeline: build, pattern status, skipped blocks, test-session flag. |
| `interrupted_trials.csv` | audit file, only if any trial was interrupted. |

## 5. From exports to results

1. Put the exports in `data/raw/` on your computer. This folder is git-ignored, so participant data stays on Drive.
2. If you have several ZIPs (one per session, or several phones), merge them:
   ```bash
   python scripts/merge_exports.py data/raw/exports/*.zip --out data/raw/session_export
   ```
   If you used a single **Export all sessions** ZIP, just unzip it into `data/raw/session_export`.
3. Fill in `participants.csv` (age, gender, gov_familiarity, used_reference_site, rank_DH/MM/ND, comments) from the Google Form.
   Add rows to `exclusions.csv`.
4. Run the pipeline:
   ```bash
   python scripts/run_pipeline.py --data-dir data/raw/session_export --out outputs/real
   ```

## 6. Updating the app on the phone

1. **Export all data first.**
2. Push the change to `main` and wait for the Deploy workflow to finish. Before pushing:
   - bump `CACHE_VERSION` in `prototype/sw.js`;
   - bump `appVersion` in `prototype/data/study.json`.
3. Open the app on the phone **with internet on**, close it fully, and open it again.
4. The home screen shows the new build number. Stored sessions are kept.

## 7. Testing on a computer

From the repo root, run:
```bash
python -m http.server 8000 -d prototype
```
Open <http://localhost:8000>. On a wide screen the app is drawn inside a fixed phone frame (390×844), so the layout
matches the phone. Opening `index.html` directly as a file does not work: the app needs a local server.

Desktop and phone keep separate data, so desktop test sessions never mix with study data.

## 8. Editing tasks and content

- **Targets and scenario text**: edit `prototype/data/study.json`. Run `pytest tests/test_prototype_config.py` afterwards.
  It checks the following:
  - every target is an L3 leaf;
  - no two targets share an L2;
  - the scenario text does not reuse menu labels;
  - the Latin square matches `pipeline/config.py`.
- **Menu tree**: edit `Navigation tree - Sheet1.csv`, then run `python scripts/build_prototype_tree.py`.
- **Current targets** (draft, chosen from the DFA tree; within a pair, the targets sit under different L1s and have matched L3 sibling counts):

| Task | Pair | Target |
| :-- | :-- | :-- |
| T1 | A | Services › Consular › Passport |
| T2 | A | About Us › DFA Compendium › Directory |
| T3 | B | Transparency › Quality & Compliance › DFA Citizen's Charter |
| T4 | B | News › Events › Rizal Day |
| T5 | C | Transparency › Procurement › Procurement Opportunities |
| T6 | C | Resources › Attached and Partner Agencies › Foreign Service Institute |

## 9. Troubleshooting

| Problem | Fix |
| :-- | :-- |
| No "Install" option on Android | Use Chrome, not an in-app browser (Messenger/Facebook). Reload once and wait for the page to finish loading. |
| App shows an old build | It updates on the second launch with internet. Close it fully and reopen it. |
| "Storage: not guaranteed" in the researcher area | Normal for some browsers. Installing the app helps, but **export after every session** either way. |
| Export does nothing on iPhone | Use the share sheet → **Save to Files** or **Drive**. Make sure you are in the home-screen app, not Safari. |
| Need to restart a participant from scratch | Researcher → **Delete** that session (type its ID), then create it again. |
