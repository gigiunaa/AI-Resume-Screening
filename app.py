from flask import Flask, request, jsonify
import zoho_api
import openai_service
import file_parser
import config
import traceback

app = Flask(__name__)


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
        name = candidate.get('Full_Name', 'Unknown')
        current_status = candidate.get('Candidate_Status', 'Unknown')
        country_raw = candidate.get('Country', '')
        country = (country_raw or '').strip().lower()

        print(f"[1] Name: {name}")
        print(f"[1] Status: {current_status}")
        print(f"[1] Country: {country_raw}")

        # 2. Find Job Opening ID
        if not jid:
            print("[2] Finding associated job...")
            jid = zoho_api.get_associated_job(cid)
            if jid:
                print(f"[2] ✅ Found: {jid}")
            else:
                print("[2] ⚠️ No associated job")

        # 3. Auto-reject by country
        if country in config.AUTO_REJECT_COUNTRIES:
            print(f"[3] ❌ Auto-reject by country: {country_raw}")
            assessment = f"Automatically rejected: candidate location ({country_raw}) is outside target geography."
            final_status = zoho_api.auto_reject_candidate(cid, jid, assessment)

            return jsonify({
                'status': 'success',
                'data': {
                    'candidate': name,
                    'job': None,
                    'score': 0,
                    'assessment': assessment,
                    'status': final_status,
                    'rejection_reason': 'country'
                }
            }), 200

        # 4. Get Job Opening
        if not jid:
            return jsonify({'error': 'No job opening ID available'}), 400

        print(f"[4] Getting job {jid}...")
        job = zoho_api.get_job_opening(jid)
        job_title = job.get('Posting_Title', 'Unknown')
        print(f"[4] Job: {job_title}")

        # 5. Get all candidate documents
        print("[5] Downloading candidate documents...")
        resume_text, all_docs_text, cv_filenames = zoho_api.get_candidate_documents(cid)

        # 6. ენის შემოწმება - მხოლოდ Resume-ზე ვამოწმებთ!
        if resume_text:
            print("[6] Checking Resume language...")
            is_english, detected_lang = file_parser.is_english_cv(resume_text)

            if not is_english:
                print(f"[6] ❌ Auto-reject: Resume is in {detected_lang}")
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

            print(f"[6] ✅ Resume language OK: {detected_lang}")
            cv_text = all_docs_text  # ყველა დოკუმენტი AI-სთვის

        elif all_docs_text:
            # Resume არ არის, მაგრამ სხვა დოკუმენტები არის
            print("[6] ⚠️ No Resume found, checking other documents...")
            is_english, detected_lang = file_parser.is_english_cv(all_docs_text)

            if not is_english:
                print(f"[6] ❌ Auto-reject: Documents in {detected_lang}")
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

            print(f"[6] ✅ Documents language OK: {detected_lang}")
            cv_text = all_docs_text

        else:
            # დოკუმენტები საერთოდ არ არის
            print("[6] ⚠️ No documents found, using ATS data only")
            cv_text = _build_fallback_cv(candidate)

        # 7. Get JD/ICP
        print("[7] Downloading JD/ICP...")
        jd_text, icp_text = zoho_api.get_job_documents(jid)

        if not jd_text:
            jd_text = job.get('Job_Description', '')

        print(f"[7] JD: {len(jd_text) if jd_text else 0} chars | ICP: {len(icp_text) if icp_text else 0} chars")

        # 8. AI Scoring
        print("[8] AI Scoring...")
        score_val, assessment = openai_service.score(
            cv_text=cv_text,
            jd_text=jd_text,
            icp_text=icp_text,
            job_info=job,
            candidate_info=candidate
        )
        print(f"[8] Score: {score_val}%")

        # 9. Apply Result
        print("[9] Applying result...")
        status_changed_to = zoho_api.apply_screening_result(cid, jid, score_val, assessment)
        final_status = status_changed_to if status_changed_to else current_status

        result = {
            'candidate': name,
            'job': job_title,
            'score': score_val,
            'assessment': assessment[:2000],
            'status': final_status,
            'rejection_reason': None
        }

        print(f"[DONE] {name} -> {score_val}% -> {final_status}")
        print(f"{'='*60}\n")

        return jsonify({'status': 'success', 'data': result}), 200

    except Exception as e:
        print(f"[ERROR] {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


def _build_fallback_cv(candidate):
    """ATS data-დან CV-ის აგება თუ ფაილი არ არის"""
    return f"""Candidate Profile:

Name: {candidate.get('Full_Name', 'N/A')}
Current Title: {candidate.get('Current_Job_Title', 'N/A')}
Experience: {candidate.get('Experience_in_Years', 'N/A')} years
Skills: {candidate.get('Skill_Set', 'N/A')}
Education: {candidate.get('Highest_Qualification_Held', 'N/A')}
English Level: {candidate.get('English_Level', 'N/A')}
Country: {candidate.get('Country', 'N/A')}

Professional Summary:
{candidate.get('Professional_Sumarry', 'N/A')}
"""


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
