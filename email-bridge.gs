/**
 * Rut Finance — email bridge v3 (Splitwise + Chase + Wells Fargo)
 *
 * Runs inside the BOT Gmail account only. Every minute it sends new
 * Splitwise and bank alert emails to Rut Finance.
 *
 * 1. Paste your API_KEY below (same value as API_KEY on Render).
 * 2. Pick "setup" in the function menu at the top and press Run, once.
 */

const APP_URL = 'https://finance-tracker-ut8h.onrender.com/api/email';
const API_KEY = 'PASTE_YOUR_API_KEY_HERE';

const SEARCH = '(splitwise OR chase OR "wells fargo" OR wellsfargo) -label:rf-done newer_than:14d';

function setup() {
  ScriptApp.getProjectTriggers().forEach(function (t) { ScriptApp.deleteTrigger(t); });
  ScriptApp.newTrigger('run').timeBased().everyMinutes(1).create();
  run();
}

function run() {
  const label = GmailApp.getUserLabelByName('rf-done') || GmailApp.createLabel('rf-done');
  const threads = GmailApp.search(SEARCH, 0, 30);

  threads.forEach(function (thread) {
    let allSent = true;
    thread.getMessages().forEach(function (m) {
      const payload = {
        key: API_KEY,
        id: m.getId(),
        from: m.getFrom(),
        subject: m.getSubject(),
        body: m.getPlainBody().slice(0, 4000),
        date: m.getDate().toISOString()
      };
      try {
        const res = UrlFetchApp.fetch(APP_URL, {
          method: 'post',
          contentType: 'application/json',
          payload: JSON.stringify(payload),
          muteHttpExceptions: true,
          followRedirects: false
        });
        const text = res.getContentText();
        let ok = false;
        try { ok = res.getResponseCode() === 200 && JSON.parse(text).ok === true; } catch (e) {}
        console.log((ok ? 'OK   ' : 'FAIL ') + res.getResponseCode() + '  ' + m.getSubject() +
                    '  ->  ' + text.slice(0, 200));
        if (!ok) allSent = false;
      } catch (e) {
        console.log('Could not reach the app (will retry): ' + e);
        allSent = false;
      }
    });
    if (allSent) thread.addLabel(label);   // failed ones retry next run
  });
}
