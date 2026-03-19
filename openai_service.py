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
    
    Args:
        cv_text: CV/Resume ტექსტი
        jd_text: Job Description ტექსტი
        icp_text: Ideal Candidate Profile ტექსტი
        job_info: Zoho Job Opening data
        candidate_info: Zoho Candidate data
    
    Returns:
        tuple: (score: int, assessment: str)
    """
    
    system = """You are an expert technical recruiter with 15+ years of experience in IT/Tech recruitment.

Your task is to provide a **rigorous, evidence-based evaluation** of the candidate against the job requirements.

═══════════════════════════════════════════════════════════════════════════════
SCORING METHODOLOGY (100 points total)
═══════════════════════════════════════════════════════════════════════════════

## 1. TECHNICAL SKILLS MATCH (40 points)

### Must-Have Skills (25 points)
- All must-haves present with proven experience: 25 pts
- 80%+ must-haves present: 18-22 pts
- 60-79% must-haves present: 12-17 pts
- 40-59% must-haves present: 6-11 pts
- <40% must-haves present: 0-5 pts

### Nice-to-Have Skills (10 points)
- Multiple nice-to-haves with experience: 8-10 pts
- Some nice-to-haves: 4-7 pts
- Few or none: 0-3 pts

### Technology Stack Alignment (5 points)
- Perfect stack match: 5 pts
- Similar technologies: 3-4 pts
- Different but transferable: 1-2 pts
- Completely different: 0 pts

---

## 2. EXPERIENCE RELEVANCE (30 points)

### Years of Experience (10 points)
- Meets or exceeds requirement: 10 pts
- Within 1 year below: 7-8 pts
- Within 2 years below: 4-6 pts
- 3+ years below requirement: 0-3 pts
- Significantly over-qualified: 6-8 pts (may not stay long)

### Industry/Domain Experience (10 points)
- Same industry with relevant projects: 10 pts
- Adjacent/related industry: 6-8 pts
- Different industry but transferable skills: 3-5 pts
- No relevant industry experience: 0-2 pts

### Role & Seniority Alignment (10 points)
- Perfect role match (same title/responsibilities): 10 pts
- Similar role, same level: 7-9 pts
- One level above/below: 4-6 pts
- Two+ levels difference: 0-3 pts

---

## 3. EDUCATION & LANGUAGES (15 points)

### Education (8 points)
- Exceeds requirements (higher degree, prestigious school): 8 pts
- Meets requirements exactly: 6-7 pts
- Close match (equivalent qualification): 4-5 pts
- Below requirements but compensated by experience: 2-3 pts
- Does not meet and no compensation: 0-1 pts

### English Proficiency (7 points)
Compare candidate's level vs job requirement:
- Meets or exceeds requirement: 7 pts
- One level below (e.g., B2 when C1 required): 3-4 pts
- Two levels below: 1-2 pts
- Three+ levels below: 0 pts

English Level Hierarchy: A1 < A2 < B1 < B2 < C1 < C2 < Native

---

## 4. CULTURE FIT & SOFT INDICATORS (15 points)

### Career Trajectory (5 points)
- Clear progression, logical career path: 5 pts
- Some progression: 3-4 pts
- Lateral moves only: 2 pts
- Unclear or concerning pattern: 0-1 pts

### Job Stability (5 points)
- 2+ years average tenure: 5 pts
- 1-2 years average: 3-4 pts
- <1 year average (job hopper): 0-2 pts

### Motivation & Fit Signals (5 points)
- Applied to matching role, location fits, salary aligned: 5 pts
- Most factors align: 3-4 pts
- Some misalignment: 1-2 pts
- Major misalignment: 0 pts

═══════════════════════════════════════════════════════════════════════════════
CRITICAL RULES & AUTOMATIC ADJUSTMENTS
═══════════════════════════════════════════════════════════════════════════════

1. **MISSING MUST-HAVE SKILLS**: If >50% of must-have skills are missing → CAP score at 45
2. **LANGUAGE BARRIER**: If English level is 2+ levels below requirement → CAP score at 55
3. **EXPERIENCE GAP**: If experience is 3+ years below requirement → CAP score at 60
4. **WRONG FIELD**: If candidate's background is in completely different field → CAP score at 30
5. **CV MISMATCH**: If CV appears to belong to different person than application → score 0-10

═══════════════════════════════════════════════════════════════════════════════
DATA PRIORITY
═══════════════════════════════════════════════════════════════════════════════

1. **ATS Application Data** = PRIMARY SOURCE (filled by candidate, verified)
2. **CV/Resume** = SECONDARY SOURCE (additional details, verify against ATS)
3. If ATS and CV conflict → Trust ATS data
4. If detail exists in ATS but not in CV → USE the ATS data, don't say "not mentioned"

═══════════════════════════════════════════════════════════════════════════════
OUTPUT FORMAT (JSON ONLY)
═══════════════════════════════════════════════════════════════════════════════

Return ONLY valid JSON with this exact structure:

{
    "score": <0-100>,
    "assessment": "<3-5 sentence detailed analysis citing specific evidence>",
    "breakdown": {
        "technical_skills": <0-40>,
        "experience": <0-30>,
        "education_language": <0-15>,
        "culture_fit": <0-15>
    },
    "strengths": ["<specific strength 1>", "<specific strength 2>", "<specific strength 3>"],
    "concerns": ["<specific concern 1>", "<specific concern 2>"],
    "missing_must_haves": ["<missing skill/requirement 1>", "<missing skill/requirement 2>"],
    "recommendation": "<STRONG_YES | YES | MAYBE | NO | STRONG_NO>"
}

═══════════════════════════════════════════════════════════════════════════════
SCORING GUIDELINES
═══════════════════════════════════════════════════════════════════════════════

- **90-100**: Exceptional match. Exceeds requirements. Interview immediately.
- **80-89**: Strong match. Meets all must-haves + most nice-to-haves. Recommend interview.
- **70-79**: Good match. Meets most requirements with minor gaps. Consider for interview.
- **60-69**: Moderate match. Notable gaps but potential. Review carefully.
- **50-59**: Weak match. Significant gaps. Only if talent pool is limited.
- **40-49**: Poor match. Missing critical requirements. Not recommended.
- **0-39**: Not suitable. Wrong field, major misalignment, or data issues.

Be rigorous but fair. Use evidence from CV and ATS data to justify every score."""

    # Build candidate profile from ATS data
    candidate_profile = f"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║  CANDIDATE APPLICATION DATA (from ATS - Primary Source)                       ║
╚═══════════════════════════════════════════════════════════════════════════════╝

BASIC INFORMATION
─────────────────
• Full Name: {_normalize(candidate_info.get('Full_Name'))}
• Location: {_normalize(candidate_info.get('City'))}, {_normalize(candidate_info.get('Country'))}
• Email: {_normalize(candidate_info.get('Email'))}

PROFESSIONAL EXPERIENCE
───────────────────────
• Total Years of Experience: {_normalize(candidate_info.get('Experience_in_Years'))}
• Current/Last Job Title: {_normalize(candidate_info.get('Current_Job_Title'))}
• Current Employer: {_normalize(candidate_info.get('Current_Employer'))}
• Current Seniority Level: {_normalize(candidate_info.get('Current_Seniority'))}
• Position Applying For: {_normalize(candidate_info.get('Position_you_are_applying_to'))}
• Industry: {_normalize(candidate_info.get('Industry'))}

SKILLS & COMPETENCIES
─────────────────────
• Primary Skill Set: {_normalize(candidate_info.get('Skill_Set'))}
• Additional Skills: {_normalize(candidate_info.get('Skills'))}

EDUCATION
─────────
• Highest Qualification: {_normalize(candidate_info.get('Highest_Qualification_Held'))}

LANGUAGES
─────────
• English Level: {_normalize(candidate_info.get('English_Level'))}
• German Level: {_normalize(candidate_info.get('German_Level'))}
• Other Languages: {_normalize(candidate_info.get('Other_Language'))}

SALARY & AVAILABILITY
─────────────────────
• Expected Salary: {_normalize(candidate_info.get('Expected_Salary'))} {_normalize(candidate_info.get('Currency'))}
• Notice Period: {_normalize(candidate_info.get('Notice_Period'))}

PROFESSIONAL SUMMARY
────────────────────
{_normalize(candidate_info.get('Professional_Sumarry'))}

ADDITIONAL INFORMATION
──────────────────────
{_normalize(candidate_info.get('Additional_Info'))}
"""

    # Build job requirements
    job_requirements = f"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║  JOB REQUIREMENTS                                                              ║
╚═══════════════════════════════════════════════════════════════════════════════╝

POSITION DETAILS
────────────────
• Job Title: {_normalize(job_info.get('Posting_Title'))}
• Seniority Level: {_normalize(job_info.get('Seniority'))}
• Department: {_normalize(job_info.get('Department_Name'))}
• Industry: {_normalize(job_info.get('Industry'))}
• Job Type: {_normalize(job_info.get('Job_Type'))}
• Remote/Location: {_normalize(job_info.get('Remote_Job'))}, {_normalize(job_info.get('City'))}, {_normalize(job_info.get('Country'))}

REQUIRED SKILLS (Must-Haves)
────────────────────────────
{_normalize(job_info.get('Required_Skills'))}

LANGUAGE REQUIREMENTS
─────────────────────
• Required English Level: {_normalize(job_info.get('English_Level'))}
• Other Required Language: {_normalize(job_info.get('Required_language'))}

EXPERIENCE REQUIREMENTS
───────────────────────
• Minimum Experience: {_normalize(job_info.get('Work_Experience'))}

SALARY RANGE
────────────
• Min: {_normalize(job_info.get('Salary_Min'))} | Max: {_normalize(job_info.get('Salary_Max'))} {_normalize(job_info.get('Currency'))}
"""

    # Build the full user message
    user_message = f"""{job_requirements}

╔═══════════════════════════════════════════════════════════════════════════════╗
║  JOB DESCRIPTION (JD)                                                          ║
╚═══════════════════════════════════════════════════════════════════════════════╝

{jd_text if jd_text else 'Not provided - evaluate based on job requirements above'}

╔═══════════════════════════════════════════════════════════════════════════════╗
║  IDEAL CANDIDATE PROFILE (ICP)                                                 ║
╚═══════════════════════════════════════════════════════════════════════════════╝

{icp_text if icp_text else 'Not provided - infer ideal candidate from job requirements'}

{candidate_profile}

╔═══════════════════════════════════════════════════════════════════════════════╗
║  CANDIDATE CV/RESUME                                                           ║
╚═══════════════════════════════════════════════════════════════════════════════╝

{cv_text if cv_text else 'No CV/Resume provided - evaluate based on ATS application data above'}

═══════════════════════════════════════════════════════════════════════════════════
TASK: Evaluate this candidate against the job requirements using the scoring methodology.
Be thorough, cite specific evidence, and provide actionable insights.
═══════════════════════════════════════════════════════════════════════════════════"""

    try:
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_message}
            ],
            temperature=0.1,
            max_tokens=2000,
            response_format={"type": "json_object"}
        )

        result = json.loads(resp.choices[0].message.content)
        
        # Extract main score
        score_val = int(result.get('score', 0))
        
        # Build comprehensive assessment
        assessment_parts = []
        
        # Main assessment
        main_assessment = result.get('assessment', 'N/A')
        assessment_parts.append(main_assessment)
        
        # Recommendation
        recommendation = result.get('recommendation', 'N/A')
        assessment_parts.append(f"\n\n📊 Recommendation: {recommendation}")
        
        # Score breakdown
        breakdown = result.get('breakdown', {})
        if breakdown:
            assessment_parts.append(
                f"\n\n📈 Score Breakdown:\n"
                f"• Technical Skills: {breakdown.get('technical_skills', 0)}/40\n"
                f"• Experience: {breakdown.get('experience', 0)}/30\n"
                f"• Education & Language: {breakdown.get('education_language', 0)}/15\n"
                f"• Culture Fit: {breakdown.get('culture_fit', 0)}/15"
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
        
        # Log for debugging
        print(f"[OpenAI] Score: {score_val}")
        print(f"[OpenAI] Recommendation: {recommendation}")
        print(f"[OpenAI] Breakdown: {breakdown}")
        print(f"[OpenAI] Strengths: {strengths}")
        print(f"[OpenAI] Concerns: {concerns}")
        print(f"[OpenAI] Missing: {missing}")
        
        return score_val, full_assessment

    except json.JSONDecodeError as e:
        print(f"[OpenAI] JSON parsing error: {e}")
        print(f"[OpenAI] Raw response: {resp.choices[0].message.content}")
        return 0, f"Error parsing AI response: {str(e)}"
    
    except Exception as e:
        print(f"[OpenAI] Error: {e}")
        return 0, f"AI scoring error: {str(e)}"


def quick_score(cv_text, jd_text, candidate_info):
    """
    სწრაფი შეფასება (მარტივი ვერსია)
    გამოიყენება როცა ICP არ არის ან სწრაფი გადაწყვეტილება გვჭირდება
    """
    system = """You are a technical recruiter. Quickly evaluate the candidate match.

Return JSON:
{
    "score": <0-100>,
    "assessment": "<2 sentences>",
    "recommendation": "<YES | NO | MAYBE>"
}

Score guide:
- 80+: Strong match, interview
- 60-79: Possible match, review
- <60: Weak match, skip"""

    user = f"""JOB: {jd_text[:2000] if jd_text else 'N/A'}

CANDIDATE:
- Name: {candidate_info.get('Full_Name', 'N/A')}
- Skills: {candidate_info.get('Skill_Set', 'N/A')}
- Experience: {candidate_info.get('Experience_in_Years', 'N/A')} years
- English: {candidate_info.get('English_Level', 'N/A')}

CV SUMMARY:
{cv_text[:3000] if cv_text else 'N/A'}

Evaluate match."""

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",  # Faster, cheaper model for quick scoring
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user}
            ],
            temperature=0,
            max_tokens=300,
            response_format={"type": "json_object"}
        )

        result = json.loads(resp.choices[0].message.content)
        return int(result.get('score', 0)), result.get('assessment', 'N/A')

    except Exception as e:
        print(f"[OpenAI] Quick score error: {e}")
        return 0, f"Error: {str(e)}"
