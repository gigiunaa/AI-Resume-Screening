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


@app.route('/test-status', methods=['POST'])
def test_status():
    """
    სტატუსის ცვლილების ტესტი — გამოიყენე debug-ისთვის
    POST /test-status {"candidate_id": "123", "status": "Rejected"}
    """
    try:
        data = request.json or {}
        cid = data.get('candidate_id')
        status = data.get('status', 'Rejected')

        if not cid:
            return jsonify({'error': 'candidate_id required'}), 400

        print(f"\n{'='*60}")
        print(f"[TEST] Testing status change for {cid} -> {status}")

        # 1. მიმდინარე სტატუსის წაკითხვა
        candidate = zoho_api.get_candidate(cid)
        current = candidate.get('Candidate_Status', 'Unknown')
        print(f"[TEST] Current status: {current}")

        # 2. მეთოდი 1: ჩვეულებრივი update
        print(f"\n[TEST] --- Method 1: Direct field update ---")
        success1, detail1 = zoho_api._update_record(cid, {
            'Candidate_Status': status
        })

        # 3. წაკითხვა ისევ
        candidate2 = zoho_api.get_candidate(cid)
        after1 = candidate2.get('Candidate_Status', 'Unknown')
        print(f"[TEST] After method 1: {after1}")

        # 4. თუ არ იმუშავა, მეთოდი 2
        if after1 != status:
            print(f"\n[TEST] --- Method 2: Action endpoint ---")
            success2 = zoho_api._change_status_via_action(cid, status)

            candidate3 = zoho_api.get_candidate(cid)
            after2 = candidate3.get('Candidate_Status', 'Unknown')
            print(f"[TEST] After method 2: {after2}")
        else:
            success2 = None
            after2 = after1

        final = after2
        worked = (final == status)

        result = {
            'candidate_id': cid,
            'requested_status': status,
            'original_status': current,
            'method_1_success': success1,
            'method_1_detail': detail1,
            'status_after_method_1': after1,
            'method_2_tried': success2 is not None,
            'method_2_success': success2,
            'final_status': final,
            'status_changed': worked
        }

        print(f"\n[TEST] RESULT: {'✅ WORKED' if worked else '❌ FAILED'}")
        print(f"{'='*60}\n")

        return jsonify(result), 200

    except Exception as e:
        print(f"[TEST ERROR] {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


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

        # 2. Auto-reject by country
        if country in config.AUTO_REJECT_COUNTRIES:
            print("[2] Country matched auto-reject list")
            assessment = "Candidate was automatically filtered out based on predefined geographic screening criteria."
            final_status = zoho_api.auto_reject_candidate(cid, assessment)

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

        # 3. Job Opening
        if not jid:
            print("[3] No job_opening_id from webhook, finding associated job...")
            associated_job = zoho_api.get_associated_job(cid)
            if not associated_job:
                return jsonify({'error': 'No associated job opening found'}), 400
            jid = associated_job.get('id')

        print(f"[3] Getting job opening {jid}...")
        job = zoho_api.get_job_opening(jid)
        job_title = job.get('Posting_Title', 'Unknown')
        print(f"[3] Job: {job_title}")

        # 4. CV
        print("[4] Downloading CV...")
        cv_content, cv_filename = zoho_api.get_candidate_cv(cid)
        cv_text = None

        if cv_content:
            cv_text = file_parser.extract_text(cv_content, cv_filename)
            print(f"[4] CV parsed: {len(cv_text) if cv_text else 0} chars")
        else:
            cv_text = f"""Name: {name}
Skills: {candidate.get('Skill_Set', 'N/A')}
Title: {candidate.get('Current_Job_Title', 'N/A')}
Experience: {candidate.get('Experience_in_Years', 'N/A')} years
Employer: {candidate.get('Current_Employer', 'N/A')}
Education: {candidate.get('Highest_Qualification', 'N/A')}
Country: {candidate.get('Country', 'N/A')}
English Level: {candidate.get('English_Level', 'N/A')}"""
            print("[4] No CV file, using Zoho parsed fields")

        # 5. JD / ICP
        print("[5] Downloading JD/ICP...")
        jd_text, icp_text = zoho_api.get_job_documents(jid)
        print(f"[5] JD: {'yes' if jd_text else 'no'} | ICP: {'yes' if icp_text else 'no'}")

        if not jd_text:
            jd_text = job.get('Job_Description', '')
            print(f"[5] Fallback: using Job_Description field ({len(jd_text) if jd_text else 0} chars)")

        # 6. AI Score
        print("[6] AI Scoring...")
        score_val, assessment = openai_service.score(
            cv_text=cv_text,
            jd_text=jd_text,
            icp_text=icp_text,
            job_info=job,
            candidate_info=candidate
        )
        print(f"[6] Score: {score_val}%")
        print(f"[6] Assessment: {assessment}")

        # 7. Apply result — ახალი გაუმჯობესებული ლოგიკა
        print("[7] Applying screening result...")
        status_changed_to = zoho_api.apply_screening_result(cid, score_val, assessment)

        final_status = status_changed_to if status_changed_to else current_status

        result = {
            'candidate': name,
            'job': job_title,
            'score': score_val,
            'assessment': assessment,
            'status': final_status,
            'status_changed': status_changed_to is not None,
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
