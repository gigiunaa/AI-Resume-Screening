# AI Resume Screener

Zoho Recruit + OpenAI powered resume screening.

## Setup

1. Deploy to Render.com
2. Add Environment Variables:
   - `ZOHO_CLIENT_ID`
   - `ZOHO_CLIENT_SECRET`
   - `ZOHO_REFRESH_TOKEN`
   - `OPENAI_API_KEY`

## Endpoints

- `GET /health` - Health check
- `GET /` - Service info
- `POST /screen` - Screen a candidate

## POST /screen Body

```json
{
  "candidate_id": "123456",
  "job_opening_id": "789012"
}
