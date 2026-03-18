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
        data = request.json
        cid = data.get('candidate_id')
        jid = data.get('job_opening_id')

        if not cid or not jid:
            return jsonify({'error': 'candidate_id and job_opening_id required'}), 400

        print(f"\n{'='*50}")
        print(f"[START] Candidate: {cid} | Job: {jid}")

        # 1. Candidate
        print("[1] Getting candidate...")
        candidate = zoho_api.get_candidate(cid)
        name = candidate.get('Full_Name', 'Unknown')
        print(f"[1] {name}")

        # 2. CV
        print("[2] Downloading CV...")
        cv_content, cv_filename = zoho_api.get_candidate_cv(cid)
        cv_text = None
        if cv_content:
            cv_text = file_parser.extract_text(cv_content, cv_filename)
            print(f"[2] CV parsed: {len(cv_text)} chars")
        else:
            cv_text = f"""Name: {name}
Skills: {candidate.get('Skill_Set', 'N/A')}
Title: {candidate.get('Current_Job_Title', 'N/A')}
Experience: {candidate.get('Experience_in_Years', 'N/A')} years
Employer: {candidate.get('Current_Employer', 'N/A')}
Education: {candidate.get('Highest_Qualification', 'N/A')}"""
            print("[2] No CV file, using Zoho parsed fields")

        # 3. Job Opening
        print("[3] Getting job opening...")
        job = zoho_api.get_job_opening(jid)
        print(f"[3] Job: {job.get('Posting_Title', 'Unknown')}")

        # 4. JD/ICP
        print("[4] Downloading JD/ICP...")
        jd_text, icp_text = zoho_api.get_job_documents(jid)
        print(f"[4] JD: {'yes' if jd_text else 'no'} | ICP: {'yes' if icp_text else 'no'}")

        # 5. AI Score
        print("[5] AI Scoring...")
        score_val, assessment = openai_service.score(cv_text, jd_text, icp_text, job)
        print(f"[5] Score: {score_val}%")

        # 6. Update Zoho
        print("[6] Updating Zoho...")
        zoho_api.update_candidate(cid, score_val, assessment)

        status = 'Rejected' if score_val < config.REJECT_THRESHOLD else 'Active'

        result = {
            'candidate': name,
            'job': job.get('Posting_Title'),
            'score': score_val,
            'assessment': assessment,
            'status': status
        }

        print(f"\n[DONE] {name} -> {score_val}% -> {status}")
        print(f"{'='*50}\n")

        return jsonify(result), 200

    except Exception as e:
        print(f"[ERROR] {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
