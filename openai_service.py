import json
from openai import OpenAI
import config

client = OpenAI(api_key=config.OPENAI_API_KEY)


def score(cv_text, jd_text, icp_text, job_info):
    system = """You are an AI resume screener for a recruitment agency.

Given a candidate's resume, Job Description (JD), and Ideal Candidate Profile (ICP),
evaluate the match.

Scoring:
- Critical requirements (must-haves): higher weight
- Preferred requirements: lower weight
- Nice-to-have: positive bonus only

Return ONLY valid JSON:
{"score": <0-100>, "assessment": "<2-3 sentences>"}"""

    user = f"""--- JOB ---
Title: {job_info.get('Posting_Title', 'N/A')}
Seniority: {job_info.get('Seniority', 'N/A')}
Required Skills: {job_info.get('Required_Skills', 'N/A')}
English Level: {job_info.get('English_Level', 'N/A')}

--- JOB DESCRIPTION ---
{jd_text or 'Not provided'}

--- IDEAL CANDIDATE PROFILE ---
{icp_text or 'Not provided'}

--- CANDIDATE RESUME ---
{cv_text or 'No resume available'}"""

    try:
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user}
            ],
            temperature=0,
            max_tokens=500,
            response_format={"type": "json_object"}
        )
        result = json.loads(resp.choices[0].message.content)
        return int(result.get('score', 0)), result.get('assessment', 'N/A')
    except Exception as e:
        print(f"[OpenAI] Error: {e}")
        return 0, f"Error: {str(e)}"
