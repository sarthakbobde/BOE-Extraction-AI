# BOE Extractor custom connector

Lets Power Automate call the BOE Extractor app running on your PC, through an on-premises data gateway.
Definition: [`apiDefinition.swagger.json`](apiDefinition.swagger.json) (OpenAPI 2.0, no authentication, `http://localhost:8770`).

## Before you start

1. Install the **on-premises data gateway** (standard mode) on the PC that runs the app, sign in with your work
   account and register it in the same region as your Power Platform environment.
2. Start the app with the Gemini key held by the server, so flows never carry it:

   ```powershell
   $env:GEMINI_API_KEY = "your-key"; .\.venv\Scripts\python run.py --port 8770
   ```

   If you use a different port, change `host` in the definition file to match.

## Import the connector

1. Power Automate → **Data** → **Custom connectors** → **New custom connector** → **Import an OpenAPI file**.
2. Name it `BOE Extractor` and choose `apiDefinition.swagger.json`.
3. **General** tab: tick **Connect via on-premises data gateway**. Scheme `HTTP`, host `localhost:8770`, base URL `/`.
4. **Security** tab: **No authentication**.
5. **Create connector**. On the **Test** tab, create a connection (pick your gateway) and run **GetConfig**:
   `serverKey` should be `true`.

## Actions

| Action | What it does |
|---|---|
| Check the app is reachable (`GetConfig`) | Connection test; shows whether the server holds a Gemini key |
| Start extracting a Bill of Entry PDF (`StartExtraction`) | Sends the PDF, returns a **Job id** immediately |
| Get extraction status (`GetJob`) | `running` / `done` / `error`, progress, cost; when done, the **Bill** and **Bill id** |
| List stored bills (`ListBills`) | Every stored bill, newest first |
| Download the original PDF (`GetSourcePdf`) | The uploaded PDF of a bill |
| Create the extracted-data PDF report (`GetReport`) | PDF report for a bill object |
| Delete a stored bill (`DeleteBill`) | Removes a bill and its PDF; cannot be undone |

## Example flow

1. **Trigger**: e.g. *When a file is created* (SharePoint / OneDrive) or *When a new email arrives* with a PDF attachment.
2. **Start extracting a Bill of Entry PDF**: *PDF file content* = the file content; *File name* = the file name.
3. **Initialize variable** `status` = `running`.
4. **Do until** `status` is not equal to `running` (limit e.g. 60 loops):
   - **Delay** 30 seconds
   - **Get extraction status** with the *Job id*
   - **Set variable** `status` = *Status*
5. **Condition** `status` = `done`:
   - Yes: use *Bill → BE number*, *Total duty*, *Fields needing review*, … (e.g. add a row to Dataverse or Excel,
     send a summary email); optionally **Create the extracted-data PDF report** with *Bill* and save the file.
   - No: notify with *Error code* / *Error message*.

## Notes

- A 19-page bill takes a few minutes; the start call returns at once, so it stays within the connector's 2-minute
  timeout. Jobs are kept in memory for one hour and are lost if the app restarts.
- Custom connectors are premium: flows started from a Power App are covered by Power Apps Premium; standalone flows
  need Power Automate Premium for the flow owner.
- The PC must be on and awake with the app running. This setup is for testing, not production.
- The app has no sign-in: anyone who can use this connection can run extractions on your Gemini key. Keep the
  connection to yourself.
