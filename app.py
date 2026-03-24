from flask import Flask, request, jsonify
import zoho_api
import openai_service
import file_parser
import config
import traceback

app = Flask(__name__)


def safe_str(value, default=''):
    """Convert Zoho field value to string, handling lists."""
    if value is None:
        return default
    if isinstance(value, list):
        return ', '.join(str(v) for v in value) if value else default
    return str(value)


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'alive'}), 200


@app.route('/', methods=['GET'])
def home():
    return jsonify({'service': 'Resume Screener', 'status': 'running'}), 200


@app.route('/screen', methods=['POST'])
def screen():
    try:
        data = request.json or {}
        cid = data.get('candidate_id')
        jid = data.get('job_opening_id')

        if not cid:
            return jsonify({'error': 'candidate_id required'}), 400

        print(f"\n{'='*60}")
        print(f"[START] Candidate: {cid} | Job: {jid or 'auto-detect'}")

        # 1. Get Candidate
        print("[1] Getting candidate...")
        candidate = zoho_api.get_candidate(cid)
        name = safe_str(candidate.get('Full_Name'), 'Unknown')
        current_status = safe_str(candidate.get('Candidate_Status'), 'Unknown')
        country_raw = safe_str(candidate.get('Country'), '')
        country = country_raw.strip().lower()

        print(f"[1] Name: {name}")
        print(f"[1] Status: {current_status}")
        print(f"[1] Country: {country_raw}")

        # 2. Find Job Opening ID
        if not jid:
            print("[2] Finding associated job...")
            jid = zoho_api.get_associated_job(cid)
            if jid:
                print(f"[2] Found: {jid}")
            else:
                print("[2] No associated job")

        # 3. Get Job Opening (needed before country check for scoring)
        if not jid:
            return jsonify({'error': 'No job opening ID available'}), 400

        print(f"[3] Getting job {jid}...")
        job = zoho_api.get_job_opening(jid)
        job_title = safe_str(job.get('Posting_Title'), 'Unknown')
        print(f"[3] Job: {job_title}")

        # 4. Get all candidate documents
        print("[4] Downloading candidate documents...")
        resume_text, all_docs_text, cv_filenames = zoho_api.get_candidate_documents(cid)

        # 5. Language check
        if resume_text:
            print("[5] Checking Resume language...")
            is_english, detected_lang = file_parser.is_english_cv(resume_text)
            if not is_english:
                print(f"[5] Auto-reject: Resume is in {detected_lang}")
                assessment = f"Automatically rejected: CV/Resume is written in {detected_lang}. Only English CVs are accepted."
                final_status = zoho_api.auto_reject_candidate(cid, jid, assessment)
                return jsonify({
                    'status': 'success',
                    'data': {
                        'candidate': name,
                        'job': job_title,
                        'score': 0,
                        'assessment': assessment,
                        'status': final_status,
                        'rejection_reason': 'cv_language',
                        'detected_language': detected_lang
                    }
                }), 200
            print(f"[5] Resume language OK: {detected_lang}")
            cv_text = all_docs_text

        elif all_docs_text:
            print("[5] No Resume found, checking other documents...")
            is_english, detected_lang = file_parser.is_english_cv(all_docs_text)
            if not is_english:
                print(f"[5] Auto-reject: Documents in {detected_lang}")
                assessment = f"Automatically rejected: Documents are written in {detected_lang}. Only English CVs are accepted."
                final_status = zoho_api.auto_reject_candidate(cid, jid, assessment)
                return jsonify({
                    'status': 'success',
                    'data': {
                        'candidate': name,
                        'job': job_title,
                        'score': 0,
                        'assessment': assessment,
                        'status': final_status,
                        'rejection_reason': 'cv_language',
                        'detected_language': detected_lang
                    }
                }), 200
            print(f"[5] Documents language OK: {detected_lang}")
            cv_text = all_docs_text

        else:
            print("[5] No documents found, using ATS data only")
            cv_text = _build_fallback_cv(candidate)

        # 6. English level check (ATS-დან)
        raw_english = candidate.get('English_Level') or ''
        if isinstance(raw_english, list):
            english_level = raw_english[0].strip() if raw_english else ''
        else:
            english_level = raw_english.strip()
        print(f"[6] English level (ATS): '{english_level}'")

        if english_level and _is_below_b2(english_level):
            print(f"[6] Auto-reject: English level {english_level} is below B2")
            assessment = (
                f"Automatically rejected: English proficiency level is {english_level}, "
                f"which is below the minimum required level (B2). "
                f"Only candidates with B2 or higher English level are accepted."
            )
            final_status = zoho_api.auto_reject_candidate(cid, jid, assessment)
            return jsonify({
                'status': 'success',
                'data': {
                    'candidate': name,
                    'job': job_title,
                    'score': 0,
                    'assessment': assessment,
                    'status': final_status,
                    'rejection_reason': 'english_level',
                    'english_level': english_level
                }
            }), 200

        print(f"[6] English level OK: {english_level or 'not specified in ATS — will check from CV'}")

        # 7. Get JD/ICP
        print("[7] Downloading JD/ICP...")
        jd_text, icp_text = zoho_api.get_job_documents(jid)
        if not jd_text:
            jd_text = safe_str(job.get('Job_Description'), '')
        print(f"[7] JD: {len(jd_text) if jd_text else 0} chars | ICP: {len(icp_text) if icp_text else 0} chars")

        # 8. AI Scoring (rubric cached per job_id)
        print("[8] AI Scoring...")
        score_val, assessment = openai_service.score(
            cv_text=cv_text,
            jd_text=jd_text,
            icp_text=icp_text,
            job_info=job,
            candidate_info=candidate,
            job_id=jid
        )
        print(f"[8] Score: {score_val}%")

        # 9. Country check — AFTER scoring
        # თუ restricted ქვეყანაა: 60+ → Associated, 0-59 → Rejected
        if country in config.AUTO_REJECT_COUNTRIES:
            print(f"[9] Restricted country: {country_raw} | Score: {score_val}")

            if score_val >= config.SAVE_FOR_FUTURE_THRESHOLD:
                # 60+ → Associated მიუხედავად ქვეყნისა
                print(f"[9] Score {score_val} >= 60 → Associated (country exception)")
                zoho_api.update_candidate_fields(cid, {
                    'AI_Score': int(score_val),
                    'AI_Assessment': assessment[:5000]
                })
                zoho_api.update_candidate_status(cid, jid, config.STATUS_ASSOCIATED)
                final_status = config.STATUS_ASSOCIATED

                return jsonify({
                    'status': 'success',
                    'data': {
                        'candidate': name,
                        'job': job_title,
                        'score': score_val,
                        'assessment': assessment[:2000],
                        'status': final_status,
                        'rejection_reason': None,
                        'country_flag': True
                    }
                }), 200

            else:
                # 0-59 → Rejected (ქვეყნის + სუსტი score)
                print(f"[9] Score {score_val} < 60 → Rejected (restricted country + weak score)")
                country_note = f"\n\nNote: Candidate is located in {country_raw}, which is outside the target geography. Additionally, the match score ({score_val}%) is below the required threshold (60%)."
                full_assessment = assessment + country_note

                zoho_api.update_candidate_fields(cid, {
                    'AI_Score': int(score_val),
                    'AI_Assessment': full_assessment[:5000]
                })
                zoho_api.update_candidate_status(cid, jid, config.STATUS_REJECTED)

                return jsonify({
                    'status': 'success',
                    'data': {
                        'candidate': name,
                        'job': job_title,
                        'score': score_val,
                        'assessment': full_assessment[:2000],
                        'status': config.STATUS_REJECTED,
                        'rejection_reason': 'country_and_score',
                        'country_flag': True
                    }
                }), 200

        # 10. Regular scoring result (non-restricted country)
        print("[10] Applying result...")
        final_status = zoho_api.apply_screening_result(cid, jid, score_val, assessment)
        if not final_status:
            final_status = current_status

        result = {
            'candidate': name,
            'job': job_title,
            'score': score_val,
            'assessment': assessment[:2000],
            'status': final_status,
            'rejection_reason': None,
            'country_flag': False
        }

        print(f"[DONE] {name} -> {score_val}% -> {final_status}")
        print(f"{'='*60}\n")

        return jsonify({'status': 'success', 'data': result}), 200

    except Exception as e:
        print(f"[ERROR] {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


def _is_below_b2(level: str) -> bool:
    """
    Returns True if English level is below B2.
    Handles CEFR format (A1, A2, B1, B2, C1, C2).
    B2, C1, C2 → OK (returns False)
    A1, A2, B1 → below B2 (returns True)
    Unknown format → False (გაატარებს, AI შეაფასებს)
    """
    normalized = level.strip().upper().replace(' ', '')
    below_b2 = {'A1', 'A2', 'B1'}
    acceptable = {'B2', 'C1', 'C2'}

    if normalized in below_b2:
        return True
    if normalized in acceptable:
        return False

    # სხვა ფორმატები (Intermediate, Advanced...) — AI-ზე გადადის
    print(f"[English] Non-CEFR format '{level}' — skipping hard reject, AI will evaluate")
    return False


def _build_fallback_cv(candidate):
    """Build a fallback CV text from ATS candidate data when no documents are available."""
    raw_english = candidate.get('English_Level', 'N/A')
    if isinstance(raw_english, list):
        english_display = ', '.join(str(v) for v in raw_english) if raw_english else 'N/A'
    else:
        english_display = raw_english or 'N/A'

    raw_skills = candidate.get('Skill_Set', 'N/A')
    if isinstance(raw_skills, list):
        skills_display = ', '.join(str(v) for v in raw_skills) if raw_skills else 'N/A'
    else:
        skills_display = raw_skills or 'N/A'

    return f"""Candidate Profile:

Name: {safe_str(candidate.get('Full_Name'), 'N/A')}
Current Title: {safe_str(candidate.get('Current_Job_Title'), 'N/A')}
Experience: {safe_str(candidate.get('Experience_in_Years'), 'N/A')} years
Skills: {skills_display}
Education: {safe_str(candidate.get('Highest_Qualification_Held'), 'N/A')}
English Level: {english_display}
Country: {safe_str(candidate.get('Country'), 'N/A')}

Professional Summary:
{safe_str(candidate.get('Professional_Sumarry'), 'N/A')}
"""


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
