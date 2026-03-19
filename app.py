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
        print(f"[START] Candidate: {cid} | Incoming Job: {jid}")

        # 1. Candidate
        print("[1] Getting candidate...")
        candidate = zoho_api.get_candidate(cid)
        name = candidate.get('Full_Name', 'Unknown')
        current_status = candidate.get('Candidate_Status', 'Unknown')
        country_raw = candidate.get('Country', '')
        country = (country_raw or '').strip().lower()

        print(f"[1] Candidate: {name}")
        print(f"[1] Current status: {current_status}")
        print(f"[1] Country: {country_raw}")

        # 2. Find job opening ID early (needed for status changes)
        if not jid:
            print("[2] No job_opening_id from webhook, finding associated job...")
            associated_job = zoho_api.get_associated_job(cid)
            if associated_job:
                jid = associated_job.get('id')
                print(f"[2] Found associated job: {jid}")
            else:
                print("[2] ⚠️ No associated job found")

        # 3. Auto-reject by country
        if country in config.AUTO_REJECT_COUNTRIES:
            print("[3] Country matched auto-reject list")
            assessment = "Candidate was automatically filtered out based on predefined geographic screening criteria."
            final_status = zoho_api.auto_reject_candidate(cid, jid, assessment)

            result = {
                'candidate': name,
                'job': None,
                'score': 0,
                'assessment': assessment,
                'status': final_status,
                'auto_rejected_by_country': True,
                'country': country_raw
            }

            print(f"[DONE] {name} -> AUTO REJECT by country -> {country_raw}")
            print(f"{'='*60}\n")
            return jsonify(result), 200

        # 4. Job Opening details
        if not jid:
            return jsonify({'error': 'No associated job opening found'}), 400

        print(f"[4] Getting job opening {jid}...")
        job = zoho_api.get_job_opening(jid)
        job_title = job.get('Posting_Title', 'Unknown')
        print(f"[4] Job: {job_title}")

        # 5. CV
        print("[5] Downloading CV...")
        cv_content, cv_filename = zoho_api.get_candidate_cv(cid)
        cv_text = None

        if cv_content:
            cv_text = file_parser.extract_text(cv_content, cv_filename)
            print(f"[5] CV parsed: {len(cv_text) if cv_text else 0} chars")
        else:
            cv_text = f"""Name: {name}
Skills: {candidate.get('Skill_Set', 'N/A')}
Title: {candidate.get('Current_Job_Title', 'N/A')}
Experience: {candidate.get('Experience_in_Years', 'N/A')} years
Employer: {candidate.get('Current_Employer', 'N/A')}
Education: {candidate.get('Highest_Qualification', 'N/A')}
Country: {candidate.get('Country', 'N/A')}
English Level: {candidate.get('English_Level', 'N/A')}"""
            print("[5] No CV file, using Zoho parsed fields")

        # 6. JD / ICP
        print("[6] Downloading JD/ICP...")
        jd_text, icp_text = zoho_api.get_job_documents(jid)
        print(f"[6] JD: {'yes' if jd_text else 'no'} | ICP: {'yes' if icp_text else 'no'}")

        if not jd_text:
            jd_text = job.get('Job_Description', '')
            print(f"[6] Fallback: using Job_Description field ({len(jd_text) if jd_text else 0} chars)")

        # 7. AI Score
        print("[7] AI Scoring...")
        score_val, assessment = openai_service.score(
            cv_text=cv_text,
            jd_text=jd_text,
            icp_text=icp_text,
            job_info=job,
            candidate_info=candidate
        )
        print(f"[7] Score: {score_val}%")

        # 8. Apply screening result — jid გადაეცემა!
        print("[8] Applying screening result...")
        status_changed_to = zoho_api.apply_screening_result(cid, jid, score_val, assessment)

        final_status = status_changed_to if status_changed_to else current_status

        result = {
            'candidate': name,
            'job': job_title,
            'score': score_val,
            'assessment': assessment,
            'status': final_status,
            'auto_rejected_by_country': False
        }

        print(f"[DONE] {name} -> {score_val}% -> {final_status}")
        print(f"{'='*60}\n")

        return jsonify(result), 200

    except Exception as e:
        print(f"[ERROR] {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
