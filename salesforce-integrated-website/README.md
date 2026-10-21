# Salesforce-style Integrated Website (Excel Database)

This project includes a Salesforce-inspired dashboard, FAQ page, and FastAPI backend.

## Excel database

The backend creates `backend/data/college_data.xlsx` automatically when it starts. It contains four sheets, similar to the workbook in your screenshot:

- **Users** — registered user records (`id`, `name`, `email`, `passwordHash`, `role`)
- **FAQs** — questions and answers (`id`, `question`, `answer`, `category`)
- **Queries** — support/query submissions (`id`, `name`, `email`, `message`, `status`, `created_at`, `phone`)
- **Announcements** — website notices (`id`, `title`, `message`, `category`, `created_at`, `status`)

The workbook is created with 30 sample FAQ questions. Keep the column headings unchanged and give each new FAQ a unique numeric ID.

### Add FAQs using Excel
1. Stop editing the workbook while the backend is writing to it.
2. Open `backend/data/college_data.xlsx` in Microsoft Excel.
3. Select the **FAQs** sheet.
4. Add a new row below the existing questions with `id`, `question`, `answer`, and `category`.
5. Save and close Excel.
6. Refresh the FAQ page. If changes don't show, restart the backend.

### Add FAQs through the API
FastAPI docs: `http://127.0.0.1:8000/docs`

`POST /api/faqs` JSON example:
```json
{
  "question": "How do I update my account?",
  "answer": "Open Accounts, select the record, choose Edit, and save.",
  "category": "Accounts"
}
```

## Run the backend

Open a terminal in the `backend` folder and run:

```powershell
python -m pip install -r requirements.txt
uvicorn main:app --reload
```

Keep the terminal running.

Useful endpoints:
- `http://127.0.0.1:8000/` — backend status
- `http://127.0.0.1:8000/api/faqs` — FAQ data
- `http://127.0.0.1:8000/docs` — interactive API docs

## Run the frontend

Open the `frontend` folder in VS Code, right-click `index.html`, and choose **Open with Live Server**. The default Live Server origin `http://127.0.0.1:5500` is allowed by the backend.

## Important notes

- Excel is a lightweight demo data store, not a production database for multiple concurrent users.
- This is a Salesforce-inspired demo. Real Salesforce account/task/report data requires Salesforce API integration.
- Do not publish or share the `Users` sheet because it contains user account data.


## Support Admin Dashboard (demo)
- Start the backend from the `backend` folder: `python -m uvicorn main:app --reload`
- Open `frontend/index.html` with VS Code Live Server.
- Choose **Support Admin** in the top navigation to view submitted queries.
- Search/filter queries and change statuses to `Open`, `In Progress`, or `Resolved`; updates are saved to `backend/data/college_data.xlsx` in the `Queries` sheet.
- API endpoint: `PATCH /api/queries/{query_id}/status` with JSON body such as `{"status":"Resolved"}`.

**Security note:** This is a college-project demo. The support admin page and query status endpoint are not protected by administrator authentication. Do not expose it publicly until role-based access control is implemented.
