import json
from openai import OpenAI
import config

client = OpenAI(api_key=config.OPENAI_API_KEY)

# Cache: {job_id: rubric_dict} — ერთი job-ისთვის ერთხელ გენერირდება
_rubric_cache = {}


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


# ─────────────────────────────────────────────
# CALL 1 — Rubric generation (cached per job)
# ─────────────────────────────────────────────

def generate_rubric(jd_text, icp_text, job_info, job_id=None):
    """
    JD + ICP-დან ამოიკითხავს:
    - job_type (tech / non-tech / finance / operations)
    - seniority (intern / junior / mid / senior / lead)
    - must_have_skills (სია — მხოლოდ ეს ითვლება score-ში)
    - nice_to_have_skills (სია — score-ში არ ითვლება, assessment-ში ჩაიწერება)
    - key_weights (technical / experience / edu_lang — სულ 100)

    Cache: თუ job_id მოწოდებულია და უკვე გამოთვლილია — cached ვერსია ბრუნდება.
    """
    if job_id and job_id in _rubric_cache:
        print(f"[Rubric] Cache hit for job {job_id}")
        return _rubric_cache[job_id]

    print(f"[Rubric] Generating rubric for job {job_id or 'unknown'}...")

    system = """You are a senior technical recruiter. Analyze the job description and ideal candidate profile, then output a structured scoring rubric in JSON.

OUTPUT FORMAT (JSON only, no extra text):
{
    "job_type": "<tech | non-tech | finance | operations>",
    "seniority": "<intern | junior | mid | senior | lead>",
    "must_have_skills": ["skill1", "skill2", ...],
    "nice_to_have_skills": ["skill1", "skill2", ...],
    "weights": {
        "technical": <integer, 0-100>,
        "experience": <integer, 0-100>,
        "edu_lang": <integer, 0-100>
    },
    "min_years_experience": <integer>,
    "english_required": "<A1|A2|B1|B2|C1|C2>",
    "notes": "<1 sentence about key focus of this role>"
}

RULES:
- weights must sum to exactly 100
- must_have_skills = only mandatory requirements from JD (no nice-to-haves)
- nice_to_have_skills = bonus skills that improve candidacy but are not required
- Adjust weights by job type:
  * tech/senior: technical 45-55, experience 30-40, edu_lang 10-20
  * tech/junior: technical 35-40, experience 15-20, edu_lang 30-40
  * non-tech/senior: technical 10-20, experience 40-50, edu_lang 25-35
  * finance/legal: technical 20-30, experience 35-45, edu_lang 25-35
  * operations: technical 15-25, experience 35-45, edu_lang 25-35
- english_required: use B2 as default if not specified"""

    user_message = f"""JOB OPENING INFO:
Position: {_normalize(job_info.get('Posting_Title'))}
Seniority: {_normalize(job_info.get('Seniority'))}
Industry: {_normalize(job_info.get('Industry'))}
Required Skills: {_normalize(job_info.get('Required_Skills'))}
Required Experience: {_normalize(job_info.get('Work_Experience'))}
Required English: {_normalize(job_info.get('English_Level'))}

JOB DESCRIPTION:
{jd_text or 'Not provided'}

IDEAL CANDIDATE PROFILE:
{icp_text or 'Not provided'}

Generate the scoring rubric for this specific role."""

    try:
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_message}
            ],
            temperature=0.1,
            max_tokens=800,
            response_format={"type": "json_object"}
        )

        rubric = json.loads(resp.choices[0].message.content)
        print(f"[Rubric] Generated: {rubric.get('job_type')} / {rubric.get('seniority')}")
        print(f"[Rubric] Must-haves: {rubric.get('must_have_skills', [])}")
        print(f"[Rubric] Weights: {rubric.get('weights', {})}")

        if job_id:
            _rubric_cache[job_id] = rubric

        return rubric

    except Exception as e:
        print(f"[Rubric] Error: {e}")
        # Fallback rubric
        return {
            "job_type": "tech",
            "seniority": "mid",
            "must_have_skills": _normalize(job_info.get('Required_Skills')).split(", "),
            "nice_to_have_skills": [],
            "weights": {"technical": 40, "experience": 30, "edu_lang": 30},
            "min_years_experience": 3,
            "english_required": "B2",
            "notes": "Fallback rubric due to generation error"
        }


# ─────────────────────────────────────────────
# CALL 2 — Candidate scoring against rubric
# ─────────────────────────────────────────────

def score_candidate(cv_text, rubric, candidate_info):
    """
    კანდიდატს აფასებს rubric-ის მიხედვით.
    Score = 0–100 (match %).
    Nice-to-have skills score-ში არ ითვლება — მხოლოდ assessment-ში ჩაიწერება.
    """

    weights = rubric.get("weights", {"technical": 40, "experience": 30, "edu_lang": 30})
    must_haves = rubric.get("must_have_skills", [])
    nice_to_haves = rubric.get("nice_to_have_skills", [])

    system = f"""You are a senior technical recruiter evaluating a candidate against a specific job rubric.

SCORING RUBRIC:
- Job type: {rubric.get('job_type')}
- Seniority level: {rubric.get('seniority')}
- Minimum experience: {rubric.get('min_years_experience')} years
- Required English: {rubric.get('english_required')}
- Role focus: {rubric.get('notes')}

MANDATORY REQUIREMENTS (score is based ONLY on these):
{json.dumps(must_haves, ensure_ascii=False)}

NICE-TO-HAVE (do NOT include in score — mention in assessment only):
{json.dumps(nice_to_haves, ensure_ascii=False)}

WEIGHT DISTRIBUTION (sums to 100):
- Technical skills match: {weights.get('technical')} points
- Experience match: {weights.get('experience')} points  
- Education & Language: {weights.get('edu_lang')} points

SCORING RULES:
1. Score ONLY against mandatory requirements — nice-to-haves must NOT affect the score
2. If >50% of must-have skills are missing → technical score MAX 40% of technical weight
3. If experience is 3+ years below requirement → experience score MAX 30% of experience weight
4. If English is below {rubric.get('english_required')} → edu_lang score MAX 20% of edu_lang weight
5. Wrong field entirely → all categories MAX 10%

OUTPUT FORMAT (JSON only):
{{
    "breakdown": {{
        "technical": <0 to {weights.get('technical')}>,
        "experience": <0 to {weights.get('experience')}>,
        "edu_lang": <0 to {weights.get('edu_lang')}>
    }},
    "assessment": "<3-5 sentences citing specific evidence from CV>",
    "strengths": ["strength 1", "strength 2"],
    "concerns": ["concern 1", "concern 2"],
    "missing_must_haves": ["missing requirement 1", ...],
    "nice_to_have_matches": ["matched bonus skill 1", ...],
    "recommendation": "<STRONG_YES | YES | MAYBE | NO | STRONG_NO>"
}}"""

    candidate_profile = f"""
CANDIDATE DATA (ATS):
Name: {_normalize(candidate_info.get('Full_Name'))}
Location: {_normalize(candidate_info.get('Country'))}, {_normalize(candidate_info.get('City'))}
Experience: {_normalize(candidate_info.get('Experience_in_Years'))} years
Current Title: {_normalize(candidate_info.get('Current_Job_Title'))}
Employer: {_normalize(candidate_info.get('Current_Employer'))}
Seniority: {_normalize(candidate_info.get('Current_Seniority'))}
Skills: {_normalize(candidate_info.get('Skill_Set'))}
Additional Skills: {_normalize(candidate_info.get('Skills'))}
Education: {_normalize(candidate_info.get('Highest_Qualification_Held'))}
English: {_normalize(candidate_info.get('English_Level'))}
Expected Salary: {_normalize(candidate_info.get('Expected_Salary'))} {_normalize(candidate_info.get('Currency'))}
Summary: {_normalize(candidate_info.get('Professional_Sumarry'))}

CV/RESUME:
{cv_text if cv_text else 'No CV provided - evaluate based on ATS data only'}"""

    try:
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": candidate_profile}
            ],
            temperature=0.1,
            max_tokens=1500,
            response_format={"type": "json_object"}
        )

        result = json.loads(resp.choices[0].message.content)
        breakdown = result.get("breakdown", {})

        technical = min(int(breakdown.get("technical", 0)), weights.get("technical", 40))
        experience = min(int(breakdown.get("experience", 0)), weights.get("experience", 30))
        edu_lang = min(int(breakdown.get("edu_lang", 0)), weights.get("edu_lang", 30))

        score_val = technical + experience + edu_lang
        score_val = max(0, min(100, score_val))

        recommendation = result.get("recommendation", "N/A")
        print(f"[Score] {score_val}/100 | {recommendation}")
        print(f"[Score] T={technical}/{weights.get('technical')} E={experience}/{weights.get('experience')} EL={edu_lang}/{weights.get('edu_lang')}")

        # Assessment აგება
        parts = [result.get("assessment", "No assessment provided.")]
        parts.append(f"\n\nRecommendation: {recommendation}")
        parts.append(
            f"\n\nScore Breakdown ({score_val}/100):\n"
            f"- Technical Skills: {technical}/{weights.get('technical')}\n"
            f"- Experience: {experience}/{weights.get('experience')}\n"
            f"- Education & Language: {edu_lang}/{weights.get('edu_lang')}"
        )

        strengths = result.get("strengths", [])
        if strengths:
            parts.append("\n\nStrengths:\n- " + "\n- ".join(strengths))

        concerns = result.get("concerns", [])
        if concerns:
            parts.append("\n\nConcerns:\n- " + "\n- ".join(concerns))

        missing = result.get("missing_must_haves", [])
        if missing:
            parts.append("\n\nMissing Requirements:\n- " + "\n- ".join(missing))

        nice_matches = result.get("nice_to_have_matches", [])
        if nice_matches:
            parts.append("\n\nBonus Skills (nice-to-have, not scored):\n- " + "\n- ".join(nice_matches))

        return score_val, "".join(parts)

    except json.JSONDecodeError as e:
        print(f"[Score] JSON error: {e}")
        return 0, f"Error parsing AI response: {str(e)}"
    except Exception as e:
        print(f"[Score] Error: {e}")
        return 0, f"AI scoring error: {str(e)}"


# ─────────────────────────────────────────────
# Main entry point (called from app.py)
# ─────────────────────────────────────────────

def score(cv_text, jd_text, icp_text, job_info, candidate_info, job_id=None):
    """
    Main function: generates rubric (cached) then scores candidate.
    """
    rubric = generate_rubric(jd_text, icp_text, job_info, job_id=job_id)
    return score_candidate(cv_text, rubric, candidate_info)
