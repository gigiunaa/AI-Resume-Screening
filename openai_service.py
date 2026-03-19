import json
from openai import OpenAI
import config

client = OpenAI(api_key=config.OPENAI_API_KEY)


def _normalize(value):
    """ველის მნიშვნელობის ნორმალიზება"""
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
    """
    კანდიდატის შეფასება AI-ით
    """
    
    system = """You are an expert technical recruiter with 15+ years of experience.

Evaluate the candidate against the job requirements using this scoring system:

═══════════════════════════════════════════════════════════════════════════════
SCORING (100 points total)
═══════════════════════════════════════════════════════════════════════════════

## 1. TECHNICAL SKILLS (40 points)
- Must-have skills present: 0-25 pts
- Nice-to-have skills: 0-10 pts  
- Technology stack match: 0-5 pts

## 2. EXPERIENCE (30 points)
- Years of experience match: 0-10 pts
- Industry experience: 0-10 pts
- Role/seniority alignment: 0-10 pts

## 3. EDUCATION & LANGUAGE (15 points)
- Education level: 0-8 pts
- English proficiency vs requirement: 0-7 pts

## 4. CULTURE FIT (15 points)
- Career trajectory: 0-5 pts
- Job stability: 0-5 pts
- Motivation signals: 0-5 pts

═══════════════════════════════════════════════════════════════════════════════
CRITICAL RULES
═══════════════════════════════════════════════════════════════════════════════

1. If >50% must-have skills missing → technical_skills MAX 15
2. If English 2+ levels below requirement → education_language MAX 5
3. If experience 3+ years below requirement → experience MAX 10
4. If CV is for wrong field entirely → all categories MAX 5 each
5. If no CV/data available → score based ONLY on available ATS data

IMPORTANT: The "score" field MUST equal the sum of all breakdown values!

═══════════════════════════════════════════════════════════════════════════════
OUTPUT FORMAT (JSON)
═══════════════════════════════════════════════════════════════════════════════

{
    "breakdown": {
        "technical_skills": <0-40>,
        "experience": <0-30>,
        "education_language": <0-15>,
        "culture_fit": <0-15>
    },
    "assessment": "<3-5 sentences with specific evidence>",
    "strengths": ["strength 1", "strength 2"],
    "concerns": ["concern 1", "concern 2"],
    "missing_must_haves": ["missing 1", "missing 2"],
    "recommendation": "<STRONG_YES | YES | MAYBE | NO | STRONG_NO>"
}

DO NOT include a separate "score" field - it will be calculated from breakdown."""

    # Candidate profile
    candidate_profile = f"""
═══ CANDIDATE DATA (ATS) ═══

Name: {_normalize(candidate_info.get('Full_Name'))}
Location: {_normalize(candidate_info.get('Country'))}, {_normalize(candidate_info.get('City'))}

Experience:
- Years: {_normalize(candidate_info.get('Experience_in_Years'))}
- Current Title: {_normalize(candidate_info.get('Current_Job_Title'))}
- Employer: {_normalize(candidate_info.get('Current_Employer'))}
- Seniority: {_normalize(candidate_info.get('Current_Seniority'))}

Skills: {_normalize(candidate_info.get('Skill_Set'))}
Additional Skills: {_normalize(candidate_info.get('Skills'))}

Education: {_normalize(candidate_info.get('Highest_Qualification_Held'))}

Languages:
- English: {_normalize(candidate_info.get('English_Level'))}
- Other: {_normalize(candidate_info.get('Other_Language'))}

Expected Salary: {_normalize(candidate_info.get('Expected_Salary'))} {_normalize(candidate_info.get('Currency'))}

Summary: {_normalize(candidate_info.get('Professional_Sumarry'))}
"""

    # Job requirements
    job_requirements = f"""
═══ JOB REQUIREMENTS ═══

Position: {_normalize(job_info.get('Posting_Title'))}
Seniority: {_normalize(job_info.get('Seniority'))}
Industry: {_normalize(job_info.get('Industry'))}

Required Skills: {_normalize(job_info.get('Required_Skills'))}

Required English: {_normalize(job_info.get('English_Level'))}
Required Experience: {_normalize(job_info.get('Work_Experience'))}
"""

    user_message = f"""{job_requirements}

═══ JOB DESCRIPTION ═══
{jd_text if jd_text else 'Not provided'}

═══ IDEAL CANDIDATE PROFILE ═══
{icp_text if icp_text else 'Not provided'}

{candidate_profile}

═══ CANDIDATE CV/RESUME ═══
{cv_text if cv_text else 'No CV provided - evaluate based on ATS data only'}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TASK: Evaluate and provide breakdown scores. Be specific and cite evidence.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""

    try:
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_message}
            ],
            temperature=0.1,
            max_tokens=1500,
            response_format={"type": "json_object"}
        )

        result = json.loads(resp.choices[0].message.content)
        
        # ✅ Score-ს ვთვლით breakdown-იდან!
        breakdown = result.get('breakdown', {})
        
        technical = int(breakdown.get('technical_skills', 0))
        experience = int(breakdown.get('experience', 0))
        edu_lang = int(breakdown.get('education_language', 0))
        culture = int(breakdown.get('culture_fit', 0))
        
        # გამოთვლილი score
        calculated_score = technical + experience + edu_lang + culture
        
        # Validation: არ უნდა გასცდეს მაქსიმუმებს
        if technical > 40:
            technical = 40
        if experience > 30:
            experience = 30
        if edu_lang > 15:
            edu_lang = 15
        if culture > 15:
            culture = 15
        
        calculated_score = technical + experience + edu_lang + culture
        
        # თუ AI-მაც მოგვცა score, შევადაროთ
        ai_score = result.get('score')
        if ai_score is not None:
            print(f"[OpenAI] AI gave score: {ai_score} | Calculated from breakdown: {calculated_score}")
        else:
            print(f"[OpenAI] Calculated score from breakdown: {calculated_score}")
        
        # ✅ საბოლოო score = გამოთვლილი breakdown-იდან
        score_val = calculated_score
        
        # Assessment-ის აგება
        assessment_parts = []
        
        # Main assessment
        assessment_parts.append(result.get('assessment', 'No assessment provided.'))
        
        # Recommendation
        recommendation = result.get('recommendation', 'N/A')
        assessment_parts.append(f"\n\n📊 Recommendation: {recommendation}")
        
        # Score breakdown
        assessment_parts.append(
            f"\n\n📈 Score Breakdown ({calculated_score}/100):\n"
            f"• Technical Skills: {technical}/40\n"
            f"• Experience: {experience}/30\n"
            f"• Education & Language: {edu_lang}/15\n"
            f"• Culture Fit: {culture}/15"
        )
        
        # Strengths
        strengths = result.get('strengths', [])
        if strengths:
            assessment_parts.append(f"\n\n✅ Strengths:\n• " + "\n• ".join(strengths))
        
        # Concerns
        concerns = result.get('concerns', [])
        if concerns:
            assessment_parts.append(f"\n\n⚠️ Concerns:\n• " + "\n• ".join(concerns))
        
        # Missing requirements
        missing = result.get('missing_must_haves', [])
        if missing:
            assessment_parts.append(f"\n\n❌ Missing Requirements:\n• " + "\n• ".join(missing))
        
        full_assessment = "".join(assessment_parts)
        
        print(f"[OpenAI] Final score: {score_val}")
        print(f"[OpenAI] Breakdown: T={technical}, E={experience}, EL={edu_lang}, C={culture}")
        
        return score_val, full_assessment

    except json.JSONDecodeError as e:
        print(f"[OpenAI] JSON error: {e}")
        return 0, f"Error parsing AI response: {str(e)}"
    
    except Exception as e:
        print(f"[OpenAI] Error: {e}")
        return 0, f"AI scoring error: {str(e)}"
