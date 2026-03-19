import requests
import config
from zoho_auth import auth


def _h():
    return {'Authorization': f'Zoho-oauthtoken {auth.get_token()}'}


def _safe_lower(value):
    """უსაფრთხოდ გარდაქმნის მნიშვნელობას lowercase string-ად"""
    if value is None:
        return ''
    if isinstance(value, dict):
        # თუ dict არის, ვეძებთ 'name' ველს
        return str(value.get('name', '')).lower().strip()
    return str(value).lower().strip()


def get_candidate(cid):
    r = requests.get(f"{config.ZOHO_RECRUIT_BASE}/Candidates/{cid}", headers=_h())
    r.raise_for_status()
    return r.json()['data'][0]


def get_job_opening(jid):
    r = requests.get(f"{config.ZOHO_RECRUIT_BASE}/Job_Openings/{jid}", headers=_h())
    r.raise_for_status()
    return r.json()['data'][0]


def get_associated_job(cid):
    """იპოვის Job Opening ID-ს რომელზეც Associated არის კანდიდატი"""
    candidate = get_candidate(cid)
    
    job_name = candidate.get('Latest_Job_Opening')
    if job_name:
        try:
            r = requests.get(
                f"{config.ZOHO_RECRUIT_BASE}/Job_Openings/search",
                headers=_h(),
                params={"criteria": f"(Posting_Title:equals:{job_name})"}
            )
            if r.status_code == 200 and r.json().get('data'):
                job_id = r.json()['data'][0]['id']
                print(f"[Zoho] Found associated job: {job_name} (ID: {job_id})")
                return job_id
        except Exception as e:
            print(f"[Zoho] Error finding job by name: {e}")
    
    print(f"[Zoho] No associated job found for candidate {cid}")
    return None


def get_attachments(module, record_id):
    r = requests.get(
        f"{config.ZOHO_RECRUIT_BASE}/{module}/{record_id}/Attachments",
        headers=_h()
    )

    if r.status_code == 204 or r.status_code == 400:
        return []

    if r.status_code != 200:
        print(f"[Zoho] Get attachments failed: {r.status_code}")
        return []

    return r.json().get('data', [])


def download_attachment(module, record_id, att_id):
    url = f"{config.ZOHO_RECRUIT_BASE}/{module}/{record_id}/Attachments/{att_id}"
    r = requests.get(url, headers=_h())

    if r.status_code == 200 and len(r.content) > 0:
        return r.content

    print(f"[Zoho] Failed to download attachment {att_id}")
    return None


def get_candidate_documents(cid):
    """
    კანდიდატის ყველა დოკუმენტის ჩამოტვირთვა და გაერთიანება.
    """
    from file_parser import extract_text
    
    attachments = get_attachments("Candidates", cid)
    
    if not attachments:
        print(f"[Zoho] No attachments for candidate {cid}")
        return None, None, None
    
    print(f"[Zoho] Found {len(attachments)} attachments")
    
    # კატეგორიზაცია
    documents = {
        'resume': [],
        'cover_letter': [],
        'portfolio': [],
        'certificate': [],
        'other': []
    }
    
    for att in attachments:
        fname = _safe_lower(att.get('File_Name', ''))
        category = _safe_lower(att.get('Category'))
        
        original_fname = att.get('File_Name', 'Unknown')
        print(f"[Zoho]   📎 {original_fname} (Category: {category or 'N/A'})")
        
        # მხოლოდ ტექსტური ფაილები
        if not any(ext in fname for ext in ['.pdf', '.docx', '.doc', '.txt', '.rtf']):
            print(f"[Zoho]     ⏭️ Skipping (not a document)")
            continue
        
        # კატეგორიზება პრიორიტეტით
        if category == 'resume' or 'resume' in fname or 'cv' in fname:
            documents['resume'].append(att)
        elif category == 'cover letter' or 'cover' in fname or 'letter' in fname:
            documents['cover_letter'].append(att)
        elif 'portfolio' in fname or category == 'portfolio':
            documents['portfolio'].append(att)
        elif 'certificate' in fname or 'cert' in fname or 'diploma' in fname or 'license' in fname:
            documents['certificate'].append(att)
        else:
            documents['other'].append(att)
    
    # ტექსტების შეგროვება
    all_texts = []
    resume_text = None
    all_filenames = []
    
    # 1. RESUME
    if documents['resume']:
        print(f"\n[Zoho] 📄 Processing RESUME files...")
        for att in documents['resume'][:2]:
            content = download_attachment("Candidates", cid, att['id'])
            if content:
                text = extract_text(content, att.get('File_Name', 'document.pdf'))
                if text and len(text) > 100:
                    section = f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  📄 RESUME: {att.get('File_Name', 'Unknown')[:60]}
╚══════════════════════════════════════════════════════════════════════════════╝

{text}
"""
                    all_texts.append(section)
                    all_filenames.append(att.get('File_Name', 'Unknown'))
                    
                    if resume_text is None:
                        resume_text = text
                    
                    print(f"[Zoho]     ✅ Added: {att.get('File_Name')} ({len(text)} chars)")
    
    # 2. COVER LETTER
    if documents['cover_letter']:
        print(f"\n[Zoho] 💌 Processing COVER LETTER files...")
        for att in documents['cover_letter'][:1]:
            content = download_attachment("Candidates", cid, att['id'])
            if content:
                text = extract_text(content, att.get('File_Name', 'document.pdf'))
                if text and len(text) > 100:
                    section = f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  💌 COVER LETTER: {att.get('File_Name', 'Unknown')[:55]}
╚══════════════════════════════════════════════════════════════════════════════╝

{text}
"""
                    all_texts.append(section)
                    all_filenames.append(att.get('File_Name', 'Unknown'))
                    print(f"[Zoho]     ✅ Added: {att.get('File_Name')} ({len(text)} chars)")
    
    # 3. PORTFOLIO
    if documents['portfolio']:
        print(f"\n[Zoho] 🎨 Processing PORTFOLIO files...")
        for att in documents['portfolio'][:1]:
            content = download_attachment("Candidates", cid, att['id'])
            if content:
                text = extract_text(content, att.get('File_Name', 'document.pdf'))
                if text and len(text) > 100:
                    section = f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  🎨 PORTFOLIO: {att.get('File_Name', 'Unknown')[:57]}
╚══════════════════════════════════════════════════════════════════════════════╝

{text}
"""
                    all_texts.append(section)
                    all_filenames.append(att.get('File_Name', 'Unknown'))
                    print(f"[Zoho]     ✅ Added: {att.get('File_Name')} ({len(text)} chars)")
    
    # 4. CERTIFICATES
    if documents['certificate']:
        print(f"\n[Zoho] 🏆 Processing CERTIFICATE files...")
        cert_texts = []
        for att in documents['certificate'][:3]:
            content = download_attachment("Candidates", cid, att['id'])
            if content:
                text = extract_text(content, att.get('File_Name', 'document.pdf'))
                if text and len(text) > 20:
                    cert_texts.append(f"• {att.get('File_Name', 'Certificate')}:\n{text[:500]}")
                    all_filenames.append(att.get('File_Name', 'Unknown'))
                    print(f"[Zoho]     ✅ Added: {att.get('File_Name')} ({len(text)} chars)")
        
        if cert_texts:
            section = f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  🏆 CERTIFICATES & CREDENTIALS
╚══════════════════════════════════════════════════════════════════════════════╝

{chr(10).join(cert_texts)}
"""
            all_texts.append(section)
    
    # 5. OTHER
    if documents['other']:
        print(f"\n[Zoho] 📁 Processing OTHER files...")
        for att in documents['other'][:2]:
            content = download_attachment("Candidates", cid, att['id'])
            if content:
                text = extract_text(content, att.get('File_Name', 'document.pdf'))
                if text and len(text) > 200:
                    section = f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  📁 ADDITIONAL DOCUMENT: {att.get('File_Name', 'Unknown')[:48]}
╚══════════════════════════════════════════════════════════════════════════════╝

{text}
"""
                    all_texts.append(section)
                    all_filenames.append(att.get('File_Name', 'Unknown'))
                    print(f"[Zoho]     ✅ Added: {att.get('File_Name')} ({len(text)} chars)")
    
    # შედეგები
    if all_texts:
        combined_text = "\n".join(all_texts)
        combined_filenames = " | ".join(all_filenames)
        
        print(f"\n[Zoho] ════════════════════════════════════════════════════════")
        print(f"[Zoho] 📊 SUMMARY: Combined {len(all_texts)} documents")
        print(f"[Zoho] 📊 Total text: {len(combined_text)} characters")
        print(f"[Zoho] 📊 Files: {combined_filenames}")
        print(f"[Zoho] ════════════════════════════════════════════════════════\n")
        
        return resume_text, combined_text, combined_filenames
    
    print(f"[Zoho] ❌ No parseable documents found for candidate {cid}")
    return None, None, None


def get_candidate_cv(cid):
    """კანდიდატის CV ტექსტის მიღება"""
    resume_text, all_docs_text, filenames = get_candidate_documents(cid)
    
    if all_docs_text:
        return all_docs_text, filenames
    
    return None, None


def get_job_documents(jid):
    from file_parser import extract_text

    attachments = get_attachments("Job_Openings", jid)
    jd_text = None
    icp_text = None

    for att in attachments:
        fname = _safe_lower(att.get('File_Name', ''))
        content = download_attachment("Job_Openings", jid, att['id'])

        if not content:
            continue

        text = extract_text(content, att.get('File_Name', 'document.pdf'))
        if not text:
            continue

        if 'jd' in fname or 'job' in fname or 'description' in fname:
            jd_text = text
        elif 'icp' in fname or 'ideal' in fname or 'profile' in fname:
            icp_text = text
        elif not jd_text:
            jd_text = text

    return jd_text, icp_text


def update_candidate_fields(cid, data):
    """AI_Score და AI_Assessment ველების განახლება"""
    r = requests.put(
        f"{config.ZOHO_RECRUIT_BASE}/Candidates/{cid}",
        headers={**_h(), 'Content-Type': 'application/json'},
        json={'data': [data]}
    )
    print(f"[Zoho] Update fields: {r.status_code}")
    return r


def update_candidate_status(cid, jid, status_value):
    """Candidate_Status-ის შეცვლა jobids-ით"""
    if not jid:
        print("[Zoho] No job_opening_id provided, trying to find it...")
        jid = get_associated_job(cid)
    
    if jid:
        payload = {
            'data': [{
                'ids': [str(cid)],
                'jobids': [str(jid)],
                'Candidate_Status': status_value
            }]
        }
        
        r = requests.put(
            f"{config.ZOHO_RECRUIT_BASE}/Candidates/status",
            headers={**_h(), 'Content-Type': 'application/json'},
            json=payload,
            timeout=30
        )
        
        print(f"[Zoho] Status update: {r.status_code}")
        
        if r.status_code == 200:
            result = r.json().get('data', [{}])[0]
            if result.get('code') == 'SUCCESS':
                print(f"[Zoho] ✅ Status → {status_value}")
                return True
            else:
                print(f"[Zoho] ❌ {result.get('message')}")
        
        return False
    
    else:
        print("[Zoho] No job found, trying direct update...")
        r = requests.put(
            f"{config.ZOHO_RECRUIT_BASE}/Candidates/{cid}",
            headers={**_h(), 'Content-Type': 'application/json'},
            json={'data': [{'Candidate_Status': status_value}]},
            timeout=30
        )
        print(f"[Zoho] Direct update: {r.status_code}")
        return r.status_code == 200


def apply_screening_result(cid, jid, score, assessment):
    """Score + Assessment შენახვა და სტატუსის ცვლილება"""
    update_candidate_fields(cid, {
        'AI_Score': int(score),
        'AI_Assessment': assessment[:5000]
    })

    if score < config.REJECT_THRESHOLD:
        print(f"[Zoho] Score {score} < {config.REJECT_THRESHOLD} -> REJECTING")
        update_candidate_status(cid, jid, config.STATUS_REJECTED)
        return config.STATUS_REJECTED

    if score < config.SAVE_FOR_FUTURE_THRESHOLD:
        print(f"[Zoho] Score {score} < {config.SAVE_FOR_FUTURE_THRESHOLD} -> SAVE FOR FUTURE")
        update_candidate_status(cid, jid, config.STATUS_SAVE_FOR_FUTURE)
        return config.STATUS_SAVE_FOR_FUTURE

    print(f"[Zoho] Score {score} >= {config.SAVE_FOR_FUTURE_THRESHOLD} -> keeping status")
    return None


def auto_reject_candidate(cid, jid, assessment):
    """ქვეყნის მიხედვით ავტო-reject"""
    update_candidate_fields(cid, {
        'AI_Score': 0,
        'AI_Assessment': assessment
    })

    update_candidate_status(cid, jid, config.STATUS_REJECTED)
    return config.STATUS_REJECTED
