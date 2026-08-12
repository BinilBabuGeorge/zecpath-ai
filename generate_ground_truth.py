"""
Builds ground-truth labels for the 7 sample resumes in data/labeled_resumes/.

IMPORTANT: these labels were written by reading each source resume directly
(see the expected_* functions below) -- NOT by running section_classifier.py
and copying its output. That's what makes the accuracy comparison in
evaluate.py meaningful rather than circular.

Each function returns a list of (line_text, expected_section) tuples for
the non-empty lines of one resume, in file order, skipping heading marker
lines (the classifier itself doesn't emit heading lines as content either).
"""

import json
from pathlib import Path

OUT_DIR = Path("data/ground_truth")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def resume_01():
    return [
        ("Name: Ananya Rao", "Other"),
        ("Designation: MERN Stack Developer", "Other"),
        ("Location: Bengaluru, India", "Other"),
        ("Email: ananya.rao@example.com", "Other"),
        ("Phone: +91-90000-00001", "Other"),
        ("Summary:", "Other"),
        ("3 years of experience building full-stack web applications using MongoDB, Express, React and Node.js.", "Other"),
        ("Skills: React.js, Node.js, Express.js, MongoDB, REST APIs, Git, Docker, JavaScript (ES6+), TypeScript", "Skills"),
        ("- Software Engineer, Brightwave Technologies (Jun 2022 - Present)", "Work Experience"),
        ("Built and maintained REST APIs serving 50k+ daily active users; led migration from JS to TypeScript.", "Work Experience"),
        ("- Junior Developer, CodeNest Pvt Ltd (Jul 2021 - May 2022)", "Work Experience"),
        ("Developed React components for an internal admin dashboard.", "Work Experience"),
        ("- B.Tech in Computer Science, VIT Vellore, 2021", "Education"),
        ("- MongoDB Certified Developer Associate (2023)", "Certifications"),
    ]


def resume_04():
    return [
        ("Name: Karthik Iyer", "Other"),
        ("Designation: Data Analyst", "Other"),
        ("Location: Chennai, India", "Other"),
        ("Email: karthik.iyer@example.com", "Other"),
        ("Phone: +91-90000-00004", "Other"),
        ("Summary:", "Other"),
        ("2.5 years analyzing business data to drive product decisions.", "Other"),
        ("Skills: SQL, Python, Power BI, Excel, Statistics, Data Visualization, Pandas", "Skills"),
        ("- Data Analyst, Finlytics Corp (Feb 2023 - Present)", "Work Experience"),
        ("Built dashboards tracking KPIs for 5 business units.", "Work Experience"),
        ("- Business Analyst Intern, Quantify Analytics (Jan 2022 - Dec 2022)", "Work Experience"),
        ("Automated monthly reporting, saving 10 hours/week.", "Work Experience"),
        ("- B.Sc in Statistics, Loyola College Chennai, 2022", "Education"),
        ("- Google Data Analytics Certificate (2022)", "Certifications"),
    ]


def resume_06():
    return [
        ("Name: Arjun Nair", "Other"),
        ("Designation: Mechanical Design Engineer", "Other"),
        ("Location: Coimbatore, India", "Other"),
        ("Email: arjun.nair@example.com", "Other"),
        ("Phone: +91-90000-00006", "Other"),
        ("Summary:", "Other"),
        ("5 years designing precision components for the automotive industry.", "Other"),
        ("Skills: AutoCAD, SolidWorks, GD&T, CNC Programming, DFMEA, Product Lifecycle Management", "Skills"),
        ("- Design Engineer, Torque Auto Components (May 2021 - Present)", "Work Experience"),
        ("Designed transmission parts reducing material cost by 12%.", "Work Experience"),
        ("- Junior Engineer, Precision Forge Ltd (Jul 2019 - Apr 2021)", "Work Experience"),
        ("Supported tooling design for 8 production lines.", "Work Experience"),
        ("- B.E. in Mechanical Engineering, PSG College of Technology, 2019", "Education"),
        ("- Certified SolidWorks Associate (2020)", "Certifications"),
    ]


def resume_09():
    return [
        ("Name: Divya Menon", "Other"),
        ("Designation: Accountant", "Other"),
        ("Location: Hyderabad, India", "Other"),
        ("Email: divya.menon@example.com", "Other"),
        ("Phone: +91-90000-00009", "Other"),
        ("Summary:", "Other"),
        ("4 years managing accounts payable/receivable and statutory compliance.", "Other"),
        ("Skills: Tally ERP, GST Filing, Excel, Accounts Reconciliation, Financial Reporting", "Skills"),
        ("- Senior Accountant, Meridian Finserv (Feb 2021 - Present)", "Work Experience"),
        ("Managed monthly closing for 3 business units; reduced reconciliation time by 30%.", "Work Experience"),
        ("- Accounts Executive, ClearBooks Pvt Ltd (Jul 2019 - Jan 2021)", "Work Experience"),
        ("Handled GST filings for 40+ client accounts.", "Work Experience"),
        ("- B.Com, Osmania University, 2019", "Education"),
        ("- Tally Certified Professional (2020)", "Certifications"),
    ]


def resume_11_no_headings():
    return [
        ("Name: Rohan Kapoor", "Other"),
        ("Designation: Backend Developer", "Other"),
        ("Location: Gurgaon, India", "Other"),
        ("Email: rohan.kapoor@example.com", "Other"),
        ("Phone: +91-90000-00011", "Other"),
        ("Backend developer with 2 years of experience building scalable APIs.", "Other"),
        ("Python, Django, PostgreSQL, Redis, Docker, AWS, Celery", "Skills"),
        ("Backend Developer, Streamline Systems (Aug 2023 - Present)", "Work Experience"),
        ("Built async task processing pipeline handling 200k jobs/day using Celery and Redis.", "Work Experience"),
        ("Software Engineer Intern, DataForge Labs (Jan 2023 - Jul 2023)", "Work Experience"),
        ("Wrote database migration scripts for a legacy PostgreSQL system.", "Work Experience"),
        ("B.Tech in Information Technology, Manipal Institute of Technology, 2022", "Education"),
        ("AWS Certified Developer Associate (2024)", "Certifications"),
    ]


def resume_12_nonstandard_headings():
    return [
        ("Name: Ishita Bansal", "Other"),
        ("Designation: Product Designer", "Other"),
        ("Location: Bengaluru, India", "Other"),
        ("Email: ishita.bansal@example.com", "Other"),
        ("Phone: +91-90000-00012", "Other"),
        ("About Me:", "Other"),
        ("Product designer passionate about accessible, data-informed design systems.", "Other"),
        ("Figma, Design Systems, Accessibility (WCAG), User Testing, Framer", "Skills"),
        ("- Product Designer, Loopwise Studio (Feb 2022 - Present)", "Work Experience"),
        ("Led the accessibility audit that brought the app to WCAG 2.1 AA compliance.", "Work Experience"),
        ("- Associate Designer, Craftbox Design (Jun 2020 - Jan 2022)", "Work Experience"),
        ("Designed the onboarding flow used by 200k+ new users.", "Work Experience"),
        ("- B.Des in Industrial Design, MIT Institute of Design, 2020", "Education"),
        ("- Certified Usability Analyst (2021)", "Certifications"),
    ]


def resume_13_with_projects():
    return [
        ("Name: Aditya Verma", "Other"),
        ("Designation: Machine Learning Engineer", "Other"),
        ("Location: Hyderabad, India", "Other"),
        ("Email: aditya.verma@example.com", "Other"),
        ("Phone: +91-90000-00013", "Other"),
        ("Summary:", "Other"),
        ("ML engineer with 3 years building recommendation and NLP systems.", "Other"),
        ("Python, PyTorch, scikit-learn, SQL, Docker, MLflow", "Skills"),
        ("- ML Engineer, VectorSpace AI (Mar 2022 - Present)", "Work Experience"),
        ("Built a product recommendation model improving click-through rate by 14%.", "Work Experience"),
        ("- Data Science Intern, Insight Analytica (Jun 2021 - Feb 2022)", "Work Experience"),
        ("Trained a churn prediction model for a subscription business.", "Work Experience"),
        ("- Resume Section Classifier: Built a rule + NLP hybrid classifier to tag resume text blocks (personal project, open source).", "Projects"),
        ("- Movie Recommender: Collaborative filtering system trained on 1M+ ratings, deployed as a Flask API.", "Projects"),
        ("- M.Tech in Artificial Intelligence, IIIT Hyderabad, 2021", "Education"),
        ("- TensorFlow Developer Certificate (2022)", "Certifications"),
    ]


def resume_14_hard_cert_no_keyword():
    return [
        ("Name: Neha Kapadia", "Other"),
        ("Designation: Cloud Solutions Engineer", "Other"),
        ("Location: Pune, India", "Other"),
        ("Email: neha.kapadia@example.com", "Other"),
        ("Phone: +91-90000-00014", "Other"),
        ("Cloud engineer with 3 years designing infrastructure on AWS and GCP.", "Other"),
        ("AWS, GCP, Terraform, Kubernetes, Python, CI/CD", "Skills"),
        ("Cloud Solutions Engineer, NimbusStack (Apr 2022 - Present)", "Work Experience"),
        ("Migrated 40+ services to a multi-region Kubernetes setup, cutting downtime by 60%.", "Work Experience"),
        ("Site Reliability Intern, GridWorks (May 2021 - Mar 2022)", "Work Experience"),
        ("Automated infrastructure provisioning using Terraform modules.", "Work Experience"),
        ("B.Tech in Computer Science, COEP Pune, 2021", "Education"),
        # NOTE: this line has no "certified/certificate" keyword -- a known
        # classifier weakness, see accuracy report.
        ("AWS Solutions Architect - Associate, Amazon Web Services (2023)", "Certifications"),
    ]


def resume_15_hard_skills_prose():
    return [
        ("Name: Vivek Chandran", "Other"),
        ("Designation: Full Stack Developer", "Other"),
        ("Location: Kochi, India", "Other"),
        ("Email: vivek.chandran@example.com", "Other"),
        ("Phone: +91-90000-00015", "Other"),
        # NOTE: skills written as a prose sentence, not a comma list -- a
        # known classifier weakness, see accuracy report.
        ("Comfortable working across the stack, mainly using React and Node on the frontend and backend, with some exposure to Docker for containerization.", "Skills"),
        ("Full Stack Developer, Coastline Software (Jan 2023 - Present)", "Work Experience"),
        ("Rebuilt the checkout flow reducing cart abandonment by 8%.", "Work Experience"),
        ("Intern, Coastline Software (Jul 2022 - Dec 2022)", "Work Experience"),
        ("Fixed cross-browser rendering bugs across the marketing site.", "Work Experience"),
        ("BCA, Cochin University of Science and Technology, 2022", "Education"),
        ("Certified Kubernetes Application Developer (2023)", "Certifications"),
    ]


GENERATORS = {
    "resume_01_mern_developer": resume_01,
    "resume_04_data_analyst": resume_04,
    "resume_06_mechanical_engineer": resume_06,
    "resume_09_accountant": resume_09,
    "resume_11_no_headings": resume_11_no_headings,
    "resume_12_nonstandard_headings": resume_12_nonstandard_headings,
    "resume_13_with_projects": resume_13_with_projects,
    "resume_14_hard_cert_no_keyword": resume_14_hard_cert_no_keyword,
    "resume_15_hard_skills_prose": resume_15_hard_skills_prose,
}

if __name__ == "__main__":
    for name, gen_fn in GENERATORS.items():
        pairs = gen_fn()
        out_path = OUT_DIR / f"{name}.json"
        out_path.write_text(
            json.dumps([{"line": l, "section": s} for l, s in pairs], indent=2),
            encoding="utf-8",
        )
        print(f"wrote {out_path} ({len(pairs)} labeled lines)")
