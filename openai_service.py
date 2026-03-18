import json
from openai import OpenAI
import config

client = OpenAI(api_key=config.OPENAI_API_KEY)


def _normalize(value):
    if value is None:
        return "N/A"

    if isinstance(value, list):
        return ", ".join(str(v) for v in value if v is not None) or "N/A"

    if isinstance(value, dict):
        if "name" in value:
            return str(value["name"])
        return json.dumps(value, ensure_ascii=False)

    return str(value)


def score(cv_text, jd_text, icp_text, job_info, candidate_info):
    system = """You are an AI resume screener for a recruitment agency.

Evaluate the candidate using BOTH:
1. structured application/ATS data
2. parsed resume/CV text

Important:
- If a detail is missing from the CV but present in the structured candidate profile, use the structured candidate profile.
- Do not say a qualification is missing if it exists in the candidate profile fields.
- Critical requirements (must-haves) carry higher weight.
- Preferred requirements carry lower weight.
- Nice-to-have items are positive bonuses.

Return ONLY valid JSON:
{"score": <0-100>, "assessment": "<2-4 sentences>"}"""

    candidate_profile = f"""--- CANDIDATE PROFILE FROM APPLICATION / ATS ---
Name: {_normalize(candidate_info.get('Full_Name'))}
Country: {_normalize(candidate_info.get('Country'))}
English Level: {_normalize(candidate_info.get('English_Level'))}
Other Language: {_normalize(candidate_info.get('Other_Language'))}
Skill Set: {_normalize(candidate_info.get('Skill_Set'))}
Skills: {_normalize(candidate_info.get('Skills'))}
Experience in Years: {_normalize(candidate_info.get('Experience_in_Years'))}
Highest Qualification Held: {_normalize(candidate_info.get('Highest_Qualification_Held'))}
Current Seniority: {_normalize(candidate_info.get('Current_Seniority'))}
Position applying to: {_normalize(candidate_info.get('Position_you_are_applying_to'))}
Additional Info: {_normalize(candidate_info.get('Additional_Info'))}
"""

    user = f"""--- JOB ---
Title: {_normalize(job_info.get('Posting_Title'))}
Seniority: {_normalize(job_info.get('Seniority'))}
Required Skills: {_normalize(job_info.get('Required_Skills'))}
English Level: {_normalize(job_info.get('English_Level'))}
Required Language: {_normalize(job_info.get('Required_language'))}
Industry: {_normalize(job_info.get('Industry'))}
Job Type: {_normalize(job_info.get('Job_Type'))}

--- JOB DESCRIPTION ---
{jd_text or 'Not provided'}

--- IDEAL CANDIDATE PROFILE ---
{icp_text or 'Not provided'}

{candidate_profile}

--- CANDIDATE RESUME ---
{cv_text or 'No resume available'}
"""

    try:
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user}
            ],
            temperature=0,
            max_tokens=600,
            response_format={"type": "json_object"}
        )

        result = json.loads(resp.choices[0].message.content)
        return int(result.get('score', 0)), result.get('assessment', 'N/A')

    except Exception as e:
        print(f"[OpenAI] Error: {e}")
        return 0, f"Error: {str(e)}"
