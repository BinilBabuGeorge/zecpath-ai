"""
Demo dataset content (Day 63), part 1: the six job descriptions and the 30 candidate personas

EVERYTHING HERE IS SYNTHETIC. Names, employers, institutes, e-mails and phone numbers are invented (e-mails use example.com, phones use a
fake 90000 range). Any match with a real person or company is a coincidence. Nothing here is real candidate data.

WHAT A PERSONA IS. One row describes one fictional applicant: who they are, what their resume says, how they answer in each round, and what
the AUTHOR expects the system to conclude (`expected`). The expectations were written BEFORE the pipeline was run on this data. They are
design intent, not human judgement, and the end-to-end run reports how many the system met and how many it did not.

HOW THE ROWS ARE USED. `parsers/demo_dataset_builder.py` turns each persona into files (a resume as DOCX or PDF, screening turns, HR and
technical answers, machine-test attempts, browser events); `parsers/demo_environment.py` runs the files through the real engines.

Input contract:  none (plain data).
Output contract: JOBS (list of dict) and PERSONAS (list of dict) with the keys described next to each.
"""

from __future__ import annotations

from typing import Any, Dict, List

AS_OF_ISO = "2026-11-21"      # the clock the whole dataset is written for; the environment freezes "today" to this date

# --------------------------------------------------------------------------------------------------------------------------- jobs
# keys: id, slug, title, role_type ("technical" / "non_technical"), domain (technical interview domain or None), file text
JOBS: List[Dict[str, Any]] = [
    {
        "id": "JOB-01", "slug": "mern_full_stack_developer", "title": "Full Stack Developer (MERN)", "role_type": "technical", "domain": "mern",
        "text": """Job Title: Full Stack Developer (MERN)
Department: Engineering
Location: Bengaluru (Hybrid)
Experience Required: 3-6 years
Employment Type: Full-time

About the Role:
Lumio Pay is a fintech start-up building payments tooling for small merchants. We need a Full Stack Developer to own features end to end across our React front end and Node.js services.

Required Skills:
- Strong proficiency in React.js and Node.js
- Hands-on experience with MongoDB and Express.js
- Experience designing and consuming REST APIs
- Working knowledge of Git and CI/CD pipelines

Good to Have:
- TypeScript
- Docker and AWS exposure

Education:
- B.Tech/B.E. in Computer Science or a related field

Responsibilities:
- Design and build REST APIs and React components
- Write tests and take part in code reviews
- Debug production issues and improve performance
- Work with product and design on new features

Salary Range: Rs 10,00,000 - Rs 18,00,000 per annum
""",
    },
    {
        "id": "JOB-02", "slug": "java_backend_developer", "title": "Java Backend Developer", "role_type": "technical", "domain": "java",
        "text": """Job Title: Java Backend Developer
Department: Platform Engineering
Location: Pune (On-site)
Experience Required: 3-5 years
Employment Type: Full-time

About the Role:
Northgate Insurance is modernising its policy-administration platform. You will build and maintain Java services that handle policy data for several million customers.

Required Skills:
- Strong core Java and Spring Boot
- Solid SQL with PostgreSQL or MySQL
- Experience building REST APIs
- Git and Docker

Good to Have:
- AWS
- Redis
- CI/CD with Jenkins

Education:
- B.Tech/B.E. in Computer Science, IT or a related field

Responsibilities:
- Develop and maintain Spring Boot microservices
- Write efficient SQL and tune slow queries
- Write unit and integration tests
- Investigate production incidents with the support team

Salary Range: Rs 9,00,000 - Rs 16,00,000 per annum
""",
    },
    {
        "id": "JOB-03", "slug": "devops_engineer", "title": "DevOps Engineer", "role_type": "technical", "domain": "devops",
        "text": """Job Title: DevOps Engineer
Department: Infrastructure
Location: Hyderabad (Hybrid)
Experience Required: 3-5 years
Employment Type: Full-time

About the Role:
Cloudharbor runs a multi-tenant analytics product on AWS. You will own our build pipelines, container platform and infrastructure code.

Required Skills:
- Linux administration
- Docker and Kubernetes
- AWS
- Infrastructure as code with Terraform
- CI/CD pipelines using Jenkins or similar

Good to Have:
- Python scripting
- Monitoring and alerting experience

Education:
- B.Tech/B.E. in any engineering discipline, or equivalent experience

Responsibilities:
- Maintain and improve CI/CD pipelines
- Manage Kubernetes clusters and deployments
- Write and review Terraform modules
- Respond to incidents and write post-incident reviews

Salary Range: Rs 12,00,000 - Rs 20,00,000 per annum
""",
    },
    {
        "id": "JOB-04", "slug": "sales_executive", "title": "Sales Executive (B2B SaaS)", "role_type": "non_technical", "domain": None,
        "text": """Job Title: Sales Executive (B2B SaaS)
Department: Sales
Location: Mumbai (Hybrid)
Experience Required: 2-4 years
Employment Type: Full-time

About the Role:
Brightdesk sells a customer-support platform to mid-sized companies. You will find new accounts, run demos and close deals.

Required Skills:
- Lead Generation and Cold Calling
- Negotiation and closing
- CRM tools such as Salesforce
- Clear written and spoken communication

Good to Have:
- Experience selling software or subscriptions
- Familiarity with email outreach tools

Education:
- Graduate in any discipline; MBA preferred

Responsibilities:
- Generate and qualify leads through calls and email
- Run product demos for prospects
- Negotiate and close deals against a quarterly target
- Keep the CRM accurate and up to date

Salary Range: Rs 6,00,000 - Rs 11,00,000 per annum plus incentives
""",
    },
    {
        "id": "JOB-05", "slug": "ui_ux_designer", "title": "UI/UX Designer", "role_type": "non_technical", "domain": None,
        "text": """Job Title: UI/UX Designer
Department: Design
Location: Chennai (Hybrid)
Experience Required: 2-5 years
Employment Type: Full-time

About the Role:
Paperleaf is a learning app used by school students. You will design flows and screens for web and mobile with a small product team.

Required Skills:
- Figma and Adobe XD
- Prototyping
- User Research and usability testing
- Design Systems

Good to Have:
- Sketch
- Basic HTML and CSS awareness

Education:
- Degree or diploma in Design, HCI or a related field

Responsibilities:
- Turn product requirements into flows, wireframes and prototypes
- Run user research sessions and share findings
- Maintain and extend our design system
- Work closely with developers during build

Salary Range: Rs 7,00,000 - Rs 14,00,000 per annum
""",
    },
    {
        "id": "JOB-06", "slug": "hr_recruiter", "title": "HR Recruiter (Talent Acquisition)", "role_type": "non_technical", "domain": None,
        "text": """Job Title: HR Recruiter (Talent Acquisition)
Department: Human Resources
Location: Delhi NCR (On-site)
Experience Required: 1-3 years
Employment Type: Full-time

About the Role:
Vantage Logistics hires several hundred people a year across operations, sales and support. You will manage hiring end to end for assigned roles.

Required Skills:
- Recruitment and candidate sourcing
- Interview coordination
- Onboarding
- Excel for tracking and reports

Good to Have:
- Experience with an applicant tracking system or HRMS
- Campus hiring

Education:
- Graduate; MBA in HR preferred

Responsibilities:
- Source and screen candidates for open roles
- Coordinate interviews with hiring managers
- Run offer and onboarding formalities
- Maintain hiring trackers and weekly reports

Salary Range: Rs 3,50,000 - Rs 6,50,000 per annum
""",
    },
]

# --------------------------------------------------------------------------------------------------------------------------- personas
# Resume experience entries: (title, company, start, end, what they did).  `end` None means "Present".
# Quality knobs (see parsers/demo_dataset_answers.py for what each level sounds like):
#   scr   screening answers : strong | ok | vague | dropped
#   hr    HR answers        : excellent | good | average | weak | nervous | limited_english
#   tech  technical answers : strong | ok | weak
#   mt    machine test      : (variant for task A, variant for task B) from strong | partial | slow | overfit | weak | skipped
# `claims_years` overrides the years the candidate SAYS in the call (the "inflater" case); None = the true figure.
# `style` is how the resume is laid out: standard | stuffed | minimal | no_headings | odd_headings | bias_header | typos
PERSONAS: List[Dict[str, Any]] = [
    # ------------------------------------------------------------------------------------------------------- JOB-01 MERN
    {"id": "DC-01", "name": "Priya Menon", "city": "Bengaluru", "job": "JOB-01", "fmt": "docx", "style": "standard", "years": 4.5,
     "scenario": "Aligned strong mid-level developer", "resume_quality": "excellent",
     "designation": "Full Stack Developer", "summary": "4.5 years building payment and dashboard products with MongoDB, Express, React and Node.js.",
     "skills": ["React.js", "Node.js", "Express.js", "MongoDB", "REST APIs", "TypeScript", "Git", "Docker", "CI/CD", "Jest"],
     "experience": [("Full Stack Developer", "Zenpay Labs", "Mar 2024", None, "Built the merchant dashboard in React and the settlement APIs in Node.js and Express for 30k merchants; cut p95 API latency by 40 percent with MongoDB index changes."),
                    ("Software Engineer", "Frontdesk Software", "Apr 2022", "Feb 2024", "Developed REST APIs and React screens for a booking product; set up the GitHub Actions CI pipeline.")],
     "education": [("B.Tech in Computer Science", "RV College of Engineering", "2021")], "certs": ["MongoDB Certified Developer Associate (2023)"],
     "scr": "strong", "hr": "excellent", "tech": "strong", "mt": ("strong", "strong"), "salary_lpa": 15, "notice_days": 60,
     "company": "Zenpay Labs", "achievement": "cut our payment API latency by about forty percent by fixing MongoDB indexes",
     "weakness": "I used to say yes to everything, so now I size work with the product manager first", "goal": "become a tech lead who mentors others",
     "project": "a merchant dashboard in React with settlement APIs in Node.js and Express on MongoDB",
     "expected": ["selected"], "rationale": "consistent, specific evidence in every round; the resume and the call agree"},
    {"id": "DC-02", "name": "Arjun Verma", "city": "Hyderabad", "job": "JOB-01", "fmt": "pdf", "style": "standard", "years": 8.0,
     "scenario": "Senior tech lead, over the 3-6 year band", "resume_quality": "excellent",
     "designation": "Lead Full Stack Engineer", "summary": "8 years in product engineering; led teams of up to 6 building multi-tenant SaaS on the MERN stack.",
     "skills": ["React.js", "Node.js", "Express.js", "MongoDB", "TypeScript", "AWS", "Docker", "Kubernetes", "REST APIs", "GraphQL", "CI/CD", "Git"],
     "experience": [("Lead Full Stack Engineer", "Stackbridge Systems", "Apr 2023", None, "Led a six-person team; designed the event-driven order service handling 2M requests a day; introduced code review standards."),
                    ("Senior Software Engineer", "Quantra Technologies", "Oct 2020", "Mar 2023", "Built the React admin platform and Node.js APIs; mentored four junior developers."),
                    ("Software Engineer", "Ledgerline", "Sep 2018", "Sep 2020", "Developed Express APIs on MongoDB for an invoicing product.")],
     "education": [("B.E. in Information Technology", "Anna University", "2016")], "certs": ["AWS Certified Developer Associate (2022)"],
     "scr": "strong", "hr": "excellent", "tech": "strong", "mt": ("strong", "strong"), "salary_lpa": 32, "notice_days": 90,
     "company": "Stackbridge Systems", "achievement": "designed an order service that now handles two million requests a day",
     "weakness": "I can over-engineer early designs, so I ask a teammate to challenge the first version", "goal": "move into an engineering manager role",
     "project": "an event-driven order service on Node.js and MongoDB with a React admin console",
     "expected": ["selected", "hold_review"], "rationale": "strong evidence; salary and seniority above the posted band justify a human look"},
    {"id": "DC-03", "name": "Sneha Kulkarni", "city": "Pune", "job": "JOB-01", "fmt": "docx", "style": "standard", "years": 0.5,
     "scenario": "Fresher with good projects", "resume_quality": "good",
     "designation": "MERN Stack Developer (Fresher)", "summary": "Recent graduate with a 6-month internship and three full-stack projects using MongoDB, Express, React and Node.js.",
     "skills": ["React.js", "Node.js", "Express.js", "MongoDB", "JavaScript", "Git", "HTML", "CSS"],
     "experience": [("Software Engineering Intern", "Pixelforge", "Jan 2026", "Jul 2026", "Built a customer feedback page in React and a small Express API; fixed 15 bugs from the team backlog.")],
     "education": [("B.Tech in Computer Science", "College of Engineering Pune", "2026")], "certs": [],
     "scr": "ok", "hr": "good", "tech": "ok", "mt": ("partial", "partial"), "salary_lpa": 5, "notice_days": 15,
     "company": "Pixelforge", "achievement": "built a feedback page that the team still uses in production",
     "weakness": "I sometimes spend too long on small details, so I now set a time box for each task", "goal": "grow into a solid backend and frontend developer",
     "project": "a task manager with login, a recipe sharing app and an expense tracker, all on the MERN stack",
     "expected": ["hold_review", "rejected"], "rationale": "relevant skills but too little experience for a 3-6 year role; a human should decide"},
    {"id": "DC-04", "name": "Rahul Desai", "city": "Mumbai", "job": "JOB-01", "fmt": "docx", "style": "stuffed", "years": 1.5,
     "scenario": "Keyword-stuffed resume, shallow interviews", "resume_quality": "poor (keyword stuffing)",
     "designation": "Full Stack Developer", "summary": "Passionate full stack developer expert in all modern technologies.",
     "skills": ["React.js", "Node.js", "Express.js", "MongoDB", "TypeScript", "Angular", "Vue.js", "Next.js", "Python", "Django", "Flask", "Java", "Spring Boot", "PHP",
                "MySQL", "PostgreSQL", "Redis", "GraphQL", "Docker", "Kubernetes", "AWS", "Azure", "GCP", "Terraform", "Jenkins", "CI/CD", "Linux", "Git", "GitHub", "jQuery",
                "REST APIs", "HTML", "CSS", "Agile", "Scrum", "Jira", "TensorFlow", "PyTorch"],
     "experience": [("Web Developer", "Brightbyte Solutions", "Jun 2025", None, "Worked on websites."),
                    ("Trainee", "Brightbyte Solutions", "Feb 2025", "May 2025", "Learned technologies.")],
     "education": [("B.Sc in Information Technology", "Mumbai University", "2024")], "certs": [],
     "scr": "vague", "hr": "weak", "tech": "weak", "mt": ("weak", "weak"), "salary_lpa": 14, "notice_days": 30,
     "company": "Brightbyte Solutions", "achievement": "worked on many projects",
     "weakness": "I am a perfectionist", "goal": "be a CTO", "project": "websites for small clients",
     "expected": ["rejected", "hold_review"], "rationale": "the resume lists everything; the interviews cannot back it up"},
    {"id": "DC-05", "name": "Ishaan Qureshi", "city": "Delhi NCR", "job": "JOB-01", "fmt": "pdf", "style": "standard", "years": 6.0,
     "scenario": "Career changer from manual QA", "resume_quality": "average",
     "designation": "Software Developer (ex-QA)", "summary": "4 years in manual and automation testing, now 2 years as a developer working in React and Node.js.",
     "skills": ["React.js", "Node.js", "JavaScript", "MongoDB", "Git", "Jira", "Selenium", "REST APIs"],
     "experience": [("Software Developer", "Craftwave Technologies", "Dec 2024", None, "Moved from QA to development; built React screens and Node.js endpoints for an HR product."),
                    ("QA Automation Engineer", "Craftwave Technologies", "Nov 2022", "Nov 2024", "Wrote Selenium suites and Postman collections for REST APIs."),
                    ("Manual Tester", "Testlane Services", "Oct 2020", "Oct 2022", "Executed regression cycles and raised defects in Jira.")],
     "education": [("B.Tech in Electronics", "Delhi Technological College", "2020")], "certs": ["ISTQB Foundation Level (2021)"],
     "scr": "ok", "hr": "good", "tech": "ok", "mt": ("strong", "partial"), "salary_lpa": 12, "notice_days": 45,
     "company": "Craftwave Technologies", "achievement": "moved from testing into development inside the same company",
     "weakness": "my backend experience is newer than my testing experience, so I am filling gaps with side projects", "goal": "become a confident full stack engineer",
     "project": "an HR leave-management screen in React with Node.js endpoints",
     "expected": ["hold_review"], "rationale": "real but partial match: the total years are high, relevant development years are about two"},
    {"id": "DC-06", "name": "Divya Pillai", "city": "Chennai", "job": "JOB-01", "fmt": "docx", "style": "standard", "years": 5.0,
     "scenario": "Strong Python backend developer, wrong stack", "resume_quality": "good",
     "designation": "Python Backend Developer", "summary": "5 years building Django and Flask services; some React for internal tools.",
     "skills": ["Python", "Django", "Flask", "PostgreSQL", "Redis", "Celery", "Docker", "AWS", "REST APIs", "Git", "CI/CD"],
     "experience": [("Senior Backend Developer", "Datacrest", "Nov 2023", None, "Owned the Django billing service; reduced nightly job time from 3 hours to 40 minutes with Celery."),
                    ("Backend Developer", "Orbitwave", "Nov 2021", "Oct 2023", "Built Flask APIs for a logistics tracker on PostgreSQL.")],
     "education": [("B.E. in Computer Science", "SSN College of Engineering", "2021")], "certs": [],
     "scr": "strong", "hr": "good", "tech": "ok", "mt": ("strong", "strong"), "salary_lpa": 18, "notice_days": 60,
     "company": "Datacrest", "achievement": "cut a nightly billing job from three hours to forty minutes",
     "weakness": "I have less React experience than backend, so I am learning it through an internal tool", "goal": "become a full stack engineer",
     "project": "a Django billing service with a small React admin tool",
     "expected": ["hold_review", "rejected"], "rationale": "a strong engineer in a different stack; the ATS should not shortlist, a human may still see value"},
    {"id": "DC-07", "name": "Karthik Subramanian", "city": "Bengaluru", "job": "JOB-01", "fmt": "docx", "style": "standard", "years": 2.5, "claims_years": 5,
     "scenario": "Inflater: says 5 years in the call, resume shows about 2.5", "resume_quality": "average",
     "designation": "Full Stack Developer", "summary": "Full stack developer with 2.5 years of experience in React and Node.js.",
     "skills": ["React.js", "Node.js", "Express.js", "MongoDB", "JavaScript", "Git", "REST APIs"],
     "experience": [("Full Stack Developer", "Appsmith Works", "May 2025", None, "Built React screens and Express endpoints for a CRM tool."),
                    ("Junior Developer", "Appsmith Works", "Apr 2024", "Apr 2025", "Fixed bugs and wrote small React components.")],
     "education": [("B.Tech in Computer Science", "PES University", "2023")], "certs": [],
     "scr": "strong", "hr": "good", "tech": "ok", "mt": ("partial", "partial"), "salary_lpa": 16, "notice_days": 30,
     "company": "Appsmith Works", "achievement": "delivered a CRM reporting module on my own",
     "weakness": "I tend to under-document my code, so I now write a short note for every pull request", "goal": "lead a small team",
     "project": "a CRM reporting module with React charts and Express endpoints",
     "expected": ["hold_review"], "rationale": "the call and the resume disagree about experience; a human must resolve it"},
    {"id": "DC-08", "name": "Anjali Bhatt", "city": "Pune", "job": "JOB-01", "fmt": "pdf", "style": "standard", "years": 3.5,
     "scenario": "Technically strong but nervous speaker", "resume_quality": "good",
     "designation": "Full Stack Developer", "summary": "3.5 years building analytics dashboards with React, Node.js and MongoDB.",
     "skills": ["React.js", "Node.js", "Express.js", "MongoDB", "REST APIs", "Git", "Docker", "TypeScript"],
     "experience": [("Full Stack Developer", "Insightly Data", "Oct 2024", None, "Built chart-heavy React dashboards and aggregation APIs on MongoDB for 200 enterprise users."),
                    ("Software Engineer", "Insightly Data", "Apr 2023", "Sep 2024", "Developed Express endpoints and unit tests.")],
     "education": [("B.E. in Computer Engineering", "Pune Institute of Technology", "2022")], "certs": [],
     "scr": "ok", "hr": "nervous", "tech": "strong", "mt": ("strong", "strong"), "salary_lpa": 14, "notice_days": 30,
     "company": "Insightly Data", "achievement": "made our slowest dashboard load in under two seconds",
     "weakness": "I get nervous speaking in interviews, so I practise with a friend", "goal": "become a senior engineer",
     "project": "analytics dashboards in React with MongoDB aggregation pipelines",
     "expected": ["selected", "hold_review"], "rationale": "strong skills; hesitant delivery should not sink an otherwise strong profile"},
    {"id": "DC-09", "name": "Vikram Singh", "city": "Delhi NCR", "job": "JOB-01", "fmt": "docx", "style": "standard", "years": 4.0,
     "scenario": "Strong scores but repeated tab switching in the machine test", "resume_quality": "good",
     "designation": "Full Stack Developer", "summary": "4 years developing web products with React, Node.js and MongoDB.",
     "skills": ["React.js", "Node.js", "Express.js", "MongoDB", "REST APIs", "Git", "CI/CD", "TypeScript"],
     "experience": [("Full Stack Developer", "Trailhead Digital", "Jun 2024", None, "Built the customer portal in React and its Express APIs; added end-to-end tests."),
                    ("Software Engineer", "Trailhead Digital", "Oct 2022", "May 2024", "Developed MongoDB-backed REST APIs.")],
     "education": [("B.Tech in Computer Science", "Amity University", "2021")], "certs": [],
     "scr": "strong", "hr": "good", "tech": "strong", "mt": ("strong", "strong"), "salary_lpa": 15, "notice_days": 30,
     "company": "Trailhead Digital", "achievement": "built the customer portal used by around ten thousand clients",
     "weakness": "I sometimes jump into code before planning, so I now sketch the design first", "goal": "become a tech lead",
     "project": "a customer portal in React with Express APIs on MongoDB",
     "integrity_events": [("tab_hidden", 140), ("tab_visible", 175), ("tab_hidden", 330), ("tab_visible", 372), ("tab_hidden", 520), ("tab_visible", 566),
                          ("window_blur", 700), ("window_focus", 738), ("tab_hidden", 905), ("tab_visible", 950)],
     "expected": ["hold_review"], "rationale": "scores are strong, but the integrity tag blocks an automatic selection and asks for a human review"},
    # ------------------------------------------------------------------------------------------------------- JOB-02 Java
    {"id": "DC-10", "name": "Nikhil Joshi", "city": "Pune", "job": "JOB-02", "fmt": "docx", "style": "standard", "years": 4.0,
     "scenario": "Aligned strong Java developer", "resume_quality": "excellent",
     "designation": "Java Backend Developer", "summary": "4 years building Spring Boot services for insurance and banking clients.",
     "skills": ["Java", "Spring Boot", "PostgreSQL", "MySQL", "REST APIs", "Docker", "Git", "Redis", "Jenkins", "AWS"],
     "experience": [("Java Backend Developer", "Meridian Financial Tech", "Jun 2024", None, "Owned the claims microservice; tuned PostgreSQL queries that cut report time from 40 seconds to 4."),
                    ("Software Engineer", "Kestrel Infosystems", "Oct 2022", "May 2024", "Built Spring Boot REST APIs and JUnit tests for a loan-origination platform.")],
     "education": [("B.E. in Computer Engineering", "Savitribai Phule Pune University", "2021")], "certs": ["Oracle Certified Associate, Java SE 11 (2022)"],
     "scr": "strong", "hr": "excellent", "tech": "strong", "mt": ("strong", "strong"), "salary_lpa": 14, "notice_days": 60,
     "company": "Meridian Financial Tech", "achievement": "reduced a claims report from forty seconds to four by tuning PostgreSQL queries",
     "weakness": "I sometimes dig too deep into one bug, so I set a time box and ask for a second pair of eyes", "goal": "grow into a senior engineer who designs services",
     "project": "a claims microservice in Spring Boot on PostgreSQL with Redis caching",
     "expected": ["selected"], "rationale": "consistent, specific evidence in every round"},
    {"id": "DC-11", "name": "Farhan Sheikh", "city": "Mumbai", "job": "JOB-02", "fmt": "docx", "style": "standard", "years": 3.0,
     "scenario": "Right keywords, shallow depth", "resume_quality": "average",
     "designation": "Java Developer", "summary": "3 years of experience in Java and Spring Boot application development.",
     "skills": ["Java", "Spring Boot", "MySQL", "REST APIs", "Git", "Docker"],
     "experience": [("Java Developer", "Bytewise Solutions", "Jan 2025", None, "Worked on Spring Boot modules and bug fixes for a retail application."),
                    ("Associate Developer", "Bytewise Solutions", "Oct 2023", "Dec 2024", "Supported Java services and wrote simple SQL queries.")],
     "education": [("B.Sc in Computer Science", "University of Mumbai", "2022")], "certs": [],
     "scr": "ok", "hr": "average", "tech": "weak", "mt": ("partial", "weak"), "salary_lpa": 10, "notice_days": 30,
     "company": "Bytewise Solutions", "achievement": "fixed a recurring checkout bug in our retail application",
     "weakness": "I need to learn performance tuning in more depth", "goal": "become a senior developer",
     "project": "a retail application with Spring Boot modules on MySQL",
     "expected": ["hold_review", "rejected"], "rationale": "the resume matches the keywords; the interviews show limited depth"},
    {"id": "DC-12", "name": "Lakshmi Iyer", "city": "Chennai", "job": "JOB-02", "fmt": "pdf", "style": "standard", "years": 4.2,
     "scenario": "Strong developer with a 14-month career gap", "resume_quality": "good",
     "designation": "Java Backend Developer", "summary": "4 years of Java and Spring Boot experience; returning after a career break to care for family.",
     "skills": ["Java", "Spring Boot", "PostgreSQL", "REST APIs", "Docker", "Git", "Jenkins", "SQL"],
     "experience": [("Senior Java Developer", "Greenfield Tech", "Sep 2025", None, "Back after a break; rebuilt the order-history service and reduced its memory use by 30 percent."),
                    ("Java Developer", "Greenfield Tech", "Jul 2021", "Jun 2024", "Built Spring Boot REST services on PostgreSQL for an e-commerce platform.")],
     "education": [("B.E. in Information Technology", "Madras Institute of Technology", "2021")], "certs": [],
     "scr": "strong", "hr": "good", "tech": "strong", "mt": ("strong", "partial"), "salary_lpa": 15, "notice_days": 30,
     "company": "Greenfield Tech", "achievement": "cut the memory use of the order-history service by about thirty percent",
     "weakness": "my newest tools knowledge needed refreshing after my break, so I completed two courses", "goal": "grow into a lead role",
     "project": "an order-history service in Spring Boot on PostgreSQL",
     "expected": ["selected", "hold_review"], "rationale": "the gap should not count against strong evidence; a human may want to ask about it"},
    {"id": "DC-13", "name": "Tarun Mehta", "city": "Pune", "job": "JOB-02", "fmt": "docx", "style": "no_headings", "years": 3.5,
     "scenario": "Good developer, resume without section headings", "resume_quality": "poor (formatting)",
     "designation": "Java Developer", "summary": "3.5 years in Java and Spring Boot development.",
     "skills": ["Java", "Spring Boot", "MySQL", "REST APIs", "Git", "Docker", "Redis"],
     "experience": [("Java Developer", "Sapphire Systems", "Oct 2024", None, "Built Spring Boot services for an inventory system and tuned MySQL queries."),
                    ("Junior Java Developer", "Sapphire Systems", "Apr 2023", "Sep 2024", "Fixed defects and wrote unit tests.")],
     "education": [("B.E. in Computer Science", "Walchand College of Engineering", "2022")], "certs": [],
     "scr": "strong", "hr": "good", "tech": "ok", "mt": ("strong", "partial"), "salary_lpa": 11, "notice_days": 45,
     "company": "Sapphire Systems", "achievement": "tuned MySQL queries and made the stock screen three times faster",
     "weakness": "I do not document enough, so I now write short design notes", "goal": "become a senior developer",
     "project": "an inventory system in Spring Boot on MySQL",
     "expected": ["hold_review", "selected"], "rationale": "a formatting problem on the resume should not hide a competent developer"},
    # ------------------------------------------------------------------------------------------------------- JOB-03 DevOps
    {"id": "DC-14", "name": "Aditya Rao", "city": "Hyderabad", "job": "JOB-03", "fmt": "docx", "style": "standard", "years": 4.0,
     "scenario": "Aligned strong DevOps engineer", "resume_quality": "excellent",
     "designation": "DevOps Engineer", "summary": "4 years automating deployments and running Kubernetes clusters on AWS.",
     "skills": ["Linux", "Docker", "Kubernetes", "AWS", "Terraform", "Jenkins", "CI/CD", "Python", "Git"],
     "experience": [("DevOps Engineer", "Skyrail Analytics", "Jun 2024", None, "Moved 30 services to Kubernetes with Terraform-managed AWS infrastructure; cut deployment time from 45 to 8 minutes."),
                    ("Systems Engineer", "Kestrel Infosystems", "Oct 2022", "May 2024", "Maintained Linux servers and Jenkins pipelines.")],
     "education": [("B.Tech in Electronics and Communication", "JNTU Hyderabad", "2021")], "certs": ["AWS Certified Solutions Architect Associate (2023)", "Certified Kubernetes Administrator (2024)"],
     "scr": "strong", "hr": "excellent", "tech": "strong", "mt": ("strong", "strong"), "salary_lpa": 18, "notice_days": 60,
     "company": "Skyrail Analytics", "achievement": "cut our deployment time from forty five minutes to eight",
     "weakness": "I automate too eagerly, so I now check that a task is repeated enough before I script it", "goal": "become a platform lead",
     "project": "a Kubernetes platform on AWS managed with Terraform and Jenkins",
     "expected": ["selected"], "rationale": "consistent, specific evidence in every round"},
    {"id": "DC-15", "name": "Pooja Hegde", "city": "Bengaluru", "job": "JOB-03", "fmt": "docx", "style": "standard", "years": 4.5,
     "scenario": "Competent engineer whose tools the ATS vocabulary does not know", "resume_quality": "good",
     "designation": "Site Reliability Engineer", "summary": "4.5 years of SRE work with Ansible, Helm, Prometheus and Grafana on Kubernetes.",
     "skills": ["Kubernetes", "Docker", "Linux", "Ansible", "Helm", "Prometheus", "Grafana", "ArgoCD", "Bash", "Python"],
     "experience": [("Site Reliability Engineer", "Nimbus Cloud", "Mar 2024", None, "Ran 12 production clusters; built Prometheus and Grafana alerting that cut paging noise by half."),
                    ("Linux Administrator", "Datagrid Services", "Apr 2022", "Feb 2024", "Automated server builds with Ansible.")],
     "education": [("B.E. in Computer Science", "BMS College of Engineering", "2021")], "certs": ["Certified Kubernetes Administrator (2023)"],
     "scr": "strong", "hr": "good", "tech": "strong", "mt": ("strong", "partial"), "salary_lpa": 18, "notice_days": 60,
     "company": "Nimbus Cloud", "achievement": "cut paging noise by half with better Prometheus and Grafana alerts",
     "weakness": "I have limited Terraform experience compared with Ansible, so I am practising on a side project", "goal": "become a principal SRE",
     "project": "twelve production Kubernetes clusters with Helm, Prometheus and Grafana",
     "expected": ["hold_review", "selected"], "rationale": "a good fit whose strongest tools (Ansible, Helm, Prometheus) are not in the ATS vocabulary"},
    {"id": "DC-16", "name": "Manoj Pandey", "city": "Hyderabad", "job": "JOB-03", "fmt": "pdf", "style": "standard", "years": 4.8,
     "scenario": "System administrator moving to cloud", "resume_quality": "average",
     "designation": "Senior Linux System Administrator", "summary": "Nearly 5 years of Linux and server administration; recently learning Docker and AWS.",
     "skills": ["Linux", "Bash", "Docker", "AWS", "Jenkins", "Git", "Nagios"],
     "experience": [("Senior System Administrator", "Metroline Services", "Oct 2024", None, "Administered 200 Linux servers; started containerising two internal tools with Docker."),
                    ("System Administrator", "Metroline Services", "Jan 2022", "Sep 2024", "Patched servers and managed backups.")],
     "education": [("B.Sc in Computer Science", "Osmania University", "2018")], "certs": ["Red Hat Certified System Administrator (2021)"],
     "scr": "ok", "hr": "average", "tech": "ok", "mt": ("partial", "weak"), "salary_lpa": 14, "notice_days": 90,
     "company": "Metroline Services", "achievement": "kept two hundred servers patched with almost no downtime",
     "weakness": "I have less hands-on Kubernetes and Terraform, which I am learning in my own lab", "goal": "move into a cloud engineering role",
     "project": "a Docker pilot for two internal tools",
     "expected": ["hold_review", "rejected"], "rationale": "strong Linux base; the cloud and infrastructure-as-code requirements are only partly met"},
    # ------------------------------------------------------------------------------------------------------- JOB-04 Sales
    {"id": "DC-17", "name": "Neha Kapoor", "city": "Mumbai", "job": "JOB-04", "fmt": "docx", "style": "standard", "years": 3.0,
     "scenario": "Aligned strong B2B SaaS seller", "resume_quality": "excellent",
     "designation": "Sales Executive", "summary": "3 years selling subscription software to mid-sized companies; consistently above target.",
     "skills": ["Lead Generation", "Cold Calling", "Negotiation", "Salesforce", "CRM", "Email Marketing"],
     "experience": [("Sales Executive", "Cloudline Software", "Jan 2025", None, "Closed 24 accounts worth Rs 1.2 crore a year; reached 118 percent of target in the last four quarters."),
                    ("Business Development Associate", "Cloudline Software", "Oct 2023", "Dec 2024", "Booked 15 qualified demos a month through calls and email.")],
     "education": [("MBA in Marketing", "NMIMS Mumbai", "2022"), ("B.Com", "Mumbai University", "2020")], "certs": ["Salesforce Administrator Fundamentals (2023)"],
     "scr": "strong", "hr": "excellent", "tech": None, "mt": None, "salary_lpa": 9, "notice_days": 30,
     "company": "Cloudline Software", "achievement": "reached one hundred and eighteen percent of target for four quarters in a row",
     "weakness": "I used to chase every lead, so I now score leads before I invest time", "goal": "become a sales team lead",
     "project": "an outbound programme that booked fifteen qualified demos a month",
     "expected": ["selected"], "rationale": "consistent, specific evidence in every round"},
    {"id": "DC-18", "name": "Sameer Khan", "city": "Mumbai", "job": "JOB-04", "fmt": "pdf", "style": "standard", "years": 2.5,
     "scenario": "Average, generic seller", "resume_quality": "average",
     "designation": "Sales Executive", "summary": "2.5 years of experience in field and inside sales.",
     "skills": ["Cold Calling", "Lead Generation", "Negotiation", "CRM"],
     "experience": [("Sales Executive", "Homeline Furnishings", "May 2025", None, "Handled walk-in and phone enquiries and converted leads to orders."),
                    ("Sales Associate", "Homeline Furnishings", "Apr 2024", "Apr 2025", "Assisted customers and updated the sales register.")],
     "education": [("B.Com", "Mumbai University", "2023")], "certs": [],
     "scr": "ok", "hr": "average", "tech": None, "mt": None, "salary_lpa": 6, "notice_days": 30,
     "company": "Homeline Furnishings", "achievement": "met my monthly target most months",
     "weakness": "I need to improve my CRM habits", "goal": "grow into a senior sales role",
     "project": "converting walk-in enquiries to orders",
     "expected": ["hold_review", "rejected"], "rationale": "relevant basics, no evidence of B2B software selling or standout results"},
    {"id": "DC-19", "name": "Riya Sharma", "city": "Delhi NCR", "job": "JOB-04", "fmt": "docx", "style": "standard", "years": 0.0,
     "scenario": "MBA fresher", "resume_quality": "good",
     "designation": "MBA Graduate (Marketing)", "summary": "Recent MBA graduate with a two-month summer internship in sales.",
     "skills": ["Lead Generation", "Cold Calling", "Negotiation", "Excel"],
     "experience": [("Sales Intern", "Brandspire", "Apr 2026", "Jun 2026", "Made 40 outreach calls a day and generated 25 qualified leads in eight weeks.")],
     "education": [("MBA in Marketing", "Symbiosis Institute of Business Management", "2026"), ("BBA", "Delhi University", "2024")], "certs": [],
     "scr": "ok", "hr": "good", "tech": None, "mt": None, "salary_lpa": 5, "notice_days": 15,
     "company": "Brandspire", "achievement": "generated twenty five qualified leads during my internship",
     "weakness": "I am still building my product knowledge, so I read the demo scripts daily", "goal": "become a strong account executive",
     "project": "a summer outreach project generating qualified leads",
     "expected": ["hold_review", "rejected"], "rationale": "promising fresher for a 2-4 year role; below the experience band"},
    {"id": "DC-20", "name": "Ajay Thomas", "city": "Kochi", "job": "JOB-04", "fmt": "docx", "style": "standard", "years": 3.0,
     "scenario": "Mismatch: HR executive applying for a sales role", "resume_quality": "good",
     "designation": "HR Executive", "summary": "3 years in HR operations, recruitment and onboarding.",
     "skills": ["Recruitment", "Onboarding", "Excel"],
     "experience": [("HR Executive", "Oceanic Hospitality", "Jan 2025", None, "Ran end-to-end recruitment for hotel staff and managed onboarding formalities."),
                    ("HR Assistant", "Oceanic Hospitality", "Oct 2023", "Dec 2024", "Maintained employee records and attendance in Excel.")],
     "education": [("MBA in Human Resources", "Rajagiri Business School", "2022")], "certs": [],
     "scr": "ok", "hr": "good", "tech": None, "mt": None, "salary_lpa": 7, "notice_days": 30,
     "company": "Oceanic Hospitality", "achievement": "filled forty hotel roles in one quarter",
     "weakness": "I have not done direct selling, which I want to try", "goal": "move into a client-facing role",
     "project": "a bulk hiring drive for hotel staff",
     "expected": ["rejected", "hold_review"], "rationale": "no sales evidence; good communication does not replace the required skills"},
    {"id": "DC-21", "name": "Gaurav Malik", "city": "Mumbai", "job": "JOB-04", "fmt": "pdf", "style": "standard", "years": 4.0,
     "scenario": "Frequent job changes, confident talker", "resume_quality": "average",
     "designation": "Sales Manager", "summary": "4 years across five sales roles in software, telecom and insurance.",
     "skills": ["Lead Generation", "Cold Calling", "Negotiation", "CRM", "Salesforce"],
     "experience": [("Sales Manager", "Telewave", "Aug 2026", None, "Leading a team of 4 on enterprise telecom accounts."),
                    ("Sales Executive", "Insureline", "Jan 2026", "Jul 2026", "Sold group insurance to corporates."),
                    ("Account Executive", "Softgrid", "Feb 2025", "Dec 2025", "Sold SaaS subscriptions to small businesses."),
                    ("Sales Executive", "Callnet", "Mar 2024", "Jan 2025", "Handled outbound calling for a broadband product."),
                    ("Business Development Associate", "Leadforge", "Nov 2022", "Feb 2024", "Qualified leads for a staffing firm.")],
     "education": [("BBA", "Mumbai University", "2022")], "certs": [],
     "scr": "strong", "hr": "good", "tech": None, "mt": None, "salary_lpa": 11, "notice_days": 30,
     "company": "Telewave", "achievement": "built a pipeline of twenty enterprise accounts in my first quarter",
     "weakness": "I move on quickly when I am not growing, and I am working on staying longer", "goal": "lead a larger team",
     "project": "an enterprise telecom pipeline",
     "expected": ["hold_review"], "rationale": "relevant skills and a strong talker, but five roles in four years need a human conversation"},
    # ------------------------------------------------------------------------------------------------------- JOB-05 UX
    {"id": "DC-22", "name": "Kavya Reddy", "city": "Chennai", "job": "JOB-05", "fmt": "docx", "style": "standard", "years": 4.0,
     "scenario": "Aligned strong product designer", "resume_quality": "excellent",
     "designation": "Product Designer", "summary": "4 years designing mobile and web products; own the design system for a learning app.",
     "skills": ["Figma", "Adobe XD", "Prototyping", "User Research", "Design Systems", "Sketch"],
     "experience": [("Product Designer", "Learnloop", "Nov 2023", None, "Built and maintained a 120-component design system in Figma; ran 25 usability sessions that cut onboarding drop-off by 18 percent."),
                    ("UI Designer", "Studio Marigold", "Nov 2022", "Oct 2023", "Designed web and mobile screens for five client apps.")],
     "education": [("Bachelor of Design", "National Institute of Design Bengaluru", "2022")], "certs": ["Google UX Design Certificate (2022)"],
     "scr": "strong", "hr": "excellent", "tech": None, "mt": None, "salary_lpa": 12, "notice_days": 60,
     "company": "Learnloop", "achievement": "cut onboarding drop-off by eighteen percent after usability testing",
     "weakness": "I used to polish too long before testing, so I now share rough flows early", "goal": "become a design lead",
     "project": "a one hundred and twenty component design system in Figma",
     "expected": ["selected"], "rationale": "consistent, specific evidence in every round"},
    {"id": "DC-23", "name": "Dev Patel", "city": "Chennai", "job": "JOB-05", "fmt": "docx", "style": "minimal", "years": 2.0,
     "scenario": "Thin resume, generic answers", "resume_quality": "poor (minimal)",
     "designation": "Graphic Designer", "summary": "Designer with 2 years of experience.",
     "skills": ["Photoshop", "Figma"],
     "experience": [("Graphic Designer", "Printwell", "Nov 2024", None, "Designed posters and banners.")],
     "education": [("Diploma in Graphic Design", "Arena Animation", "2024")], "certs": [],
     "scr": "vague", "hr": "weak", "tech": None, "mt": None, "salary_lpa": 8, "notice_days": 15,
     "company": "Printwell", "achievement": "designed many posters",
     "weakness": "I work too hard", "goal": "be a good designer", "project": "posters and banners",
     "expected": ["rejected", "hold_review"], "rationale": "the resume and the answers give little evidence of product design work"},
    {"id": "DC-24", "name": "Shreya Banerjee", "city": "Chennai", "job": "JOB-05", "fmt": "pdf", "style": "standard", "years": 5.5,
     "scenario": "Strong designer returning after a two-year break", "resume_quality": "good",
     "designation": "UX Designer", "summary": "5.5 years in UX design; returning after a two-year career break.",
     "skills": ["Figma", "Adobe XD", "Prototyping", "User Research", "Design Systems", "Sketch"],
     "experience": [("UX Designer", "Freelance and volunteer projects", "Jan 2025", None, "Redesigned the booking flow for a non-profit clinic; ran six usability tests."),
                    ("UX Designer", "Quicklane Apps", "Jun 2019", "Dec 2022", "Designed the rider app flows and led research for a ride-hailing start-up.")],
     "education": [("Master of Design (HCI)", "IIT Guwahati", "2019")], "certs": [],
     "scr": "strong", "hr": "good", "tech": None, "mt": None, "salary_lpa": 11, "notice_days": 15,
     "company": "Quicklane Apps", "achievement": "led the research that simplified our rider sign-up flow",
     "weakness": "my tools knowledge needed refreshing after my break, so I rebuilt a portfolio project", "goal": "return to a full-time product design role",
     "project": "a clinic booking flow redesign tested with six users",
     "expected": ["selected", "hold_review"], "rationale": "the gap should not count against strong evidence; a human may want to ask about it"},
    {"id": "DC-25", "name": "Omar Siddiqui", "city": "Chennai", "job": "JOB-05", "fmt": "docx", "style": "typos", "years": 3.0,
     "scenario": "Capable designer, careless resume (typos, no headings)", "resume_quality": "poor (typos)",
     "designation": "UI/UX Desinger", "summary": "3 year experiance in UI UX desgin for web and mobile aplications.",
     "skills": ["Figma", "Adobe XD", "Prototyping", "User Research"],
     "experience": [("UI/UX Desinger", "Pixelnest", "Jan 2025", None, "Desgined mobile app screens and made prototypes in Figma for a food delivery startup."),
                    ("Junior Desinger", "Pixelnest", "Oct 2023", "Dec 2024", "Made wireframes and helped in user reserch.")],
     "education": [("Bachlor of Design", "Anna University", "2022")], "certs": [],
     "scr": "ok", "hr": "good", "tech": None, "mt": None, "salary_lpa": 8, "notice_days": 30,
     "company": "Pixelnest", "achievement": "designed the ordering flow used by about fifty thousand customers",
     "weakness": "I make small mistakes in my documents, so I now ask a colleague to proofread", "goal": "become a senior designer",
     "project": "a food delivery ordering flow prototyped in Figma",
     "expected": ["hold_review", "selected"], "rationale": "typos on a resume are a signal for a recruiter to read, not a reason to reject a designer outright"},
    # ------------------------------------------------------------------------------------------------------- JOB-06 HR
    {"id": "DC-26", "name": "Sunita Rajan", "city": "Delhi NCR", "job": "JOB-06", "fmt": "docx", "style": "standard", "years": 3.0,
     "scenario": "Aligned strong talent acquisition executive", "resume_quality": "excellent",
     "designation": "Talent Acquisition Executive", "summary": "3 years of end-to-end recruitment for operations and sales roles in logistics.",
     "skills": ["Recruitment", "Candidate Sourcing", "Onboarding", "Excel", "Interview Coordination", "Naukri", "LinkedIn Recruiter"],
     "experience": [("Talent Acquisition Executive", "Fleetwise Logistics", "Jan 2025", None, "Closed 180 hires a year across operations and sales; cut time-to-hire from 38 to 26 days."),
                    ("HR Recruiter", "Fleetwise Logistics", "Oct 2023", "Dec 2024", "Sourced and screened candidates and coordinated interviews.")],
     "education": [("MBA in Human Resources", "Delhi School of Management", "2022")], "certs": [],
     "scr": "strong", "hr": "excellent", "tech": None, "mt": None, "salary_lpa": 6, "notice_days": 30,
     "company": "Fleetwise Logistics", "achievement": "cut our time to hire from thirty eight days to twenty six",
     "weakness": "I used to over-screen on paper, so I now call candidates before I reject", "goal": "become a talent acquisition lead",
     "project": "a bulk hiring programme that closed a hundred and eighty hires a year",
     "expected": ["selected"], "rationale": "consistent, specific evidence in every round"},
    {"id": "DC-27", "name": "Amit Chawla", "city": "Delhi NCR", "job": "JOB-06", "fmt": "pdf", "style": "standard", "years": 1.5,
     "scenario": "Average recruiter, limited detail", "resume_quality": "average",
     "designation": "HR Executive", "summary": "1.5 years in recruitment and HR operations.",
     "skills": ["Recruitment", "Onboarding", "Excel"],
     "experience": [("HR Executive", "Maxcare Services", "May 2025", None, "Recruitment, interview scheduling and onboarding for a small team.")],
     "education": [("BBA", "Guru Gobind Singh University", "2024")], "certs": [],
     "scr": "ok", "hr": "average", "tech": None, "mt": None, "salary_lpa": 4, "notice_days": 30,
     "company": "Maxcare Services", "achievement": "helped hire around thirty people",
     "weakness": "I need to learn more about sourcing tools", "goal": "grow in talent acquisition",
     "project": "scheduling interviews and onboarding new joiners",
     "expected": ["hold_review", "selected"], "rationale": "meets the basics for a 1-3 year role without distinguishing evidence"},
    {"id": "DC-28", "name": "Harish Bhandari", "city": "Delhi NCR", "job": "JOB-06", "fmt": "docx", "style": "bias_header", "years": 2.5,
     "scenario": "Resume with a full demographic header (fairness check)", "resume_quality": "good",
     "designation": "HR Recruiter", "summary": "2.5 years of recruitment experience in the retail sector.",
     "skills": ["Recruitment", "Candidate Sourcing", "Onboarding", "Excel", "Interview Coordination"],
     "experience": [("HR Recruiter", "Shoplane Retail", "Sep 2025", None, "Hired store staff and managers across six cities; maintained the hiring tracker in Excel."),
                    ("HR Intern", "Shoplane Retail", "Oct 2024", "Aug 2025", "Screened resumes and scheduled interviews.")],
     "education": [("BBA", "IP University", "2024")], "certs": [],
     "scr": "strong", "hr": "good", "tech": None, "mt": None, "salary_lpa": 5, "notice_days": 30,
     "company": "Shoplane Retail", "achievement": "hired store staff in six cities within one quarter",
     "weakness": "I sometimes take on too many requisitions at once, so I now prioritise with managers", "goal": "become a talent acquisition specialist",
     "project": "a multi-city retail hiring drive",
     "expected": ["selected", "hold_review"], "rationale": "personal details must not affect the result: compare with an identical resume without the header"},
    {"id": "DC-29", "name": "Fatima Noor", "city": "Delhi NCR", "job": "JOB-06", "fmt": "docx", "style": "standard", "years": 2.5,
     "scenario": "Strong recruiter, limited English and a noisy line", "resume_quality": "good",
     "designation": "HR Recruiter", "summary": "2.5 years in recruitment and joining formalities for BPO and support teams.",
     "skills": ["Recruitment", "Candidate Sourcing", "Onboarding", "Excel", "Interview Coordination"],
     "experience": [("HR Recruiter", "Callbridge BPO", "May 2025", None, "Hired 25 agents a month for voice-support campaigns; ran induction batches."),
                    ("HR Trainee", "Callbridge BPO", "Apr 2024", "Apr 2025", "Screened candidates and updated trackers.")],
     "education": [("B.A. in Sociology", "Jamia Millia Islamia", "2023")], "certs": [],
     "scr": "ok", "hr": "limited_english", "tech": None, "mt": None, "salary_lpa": 5, "notice_days": 30, "scr_confidence": 0.58,
     "company": "Callbridge BPO", "achievement": "hired twenty five agents every month for our support campaigns",
     "weakness": "my English is improving and I practise every day", "goal": "become a senior recruiter",
     "project": "monthly agent hiring for voice-support campaigns",
     "expected": ["hold_review", "selected"], "rationale": "weak speech recognition and limited English should lead to a human review, not a rejection"},
    {"id": "DC-30", "name": "Jasmine D'Souza", "city": "Delhi NCR", "job": "JOB-06", "fmt": "pdf", "style": "standard", "years": 3.0,
     "scenario": "The call drops after three questions", "resume_quality": "good",
     "designation": "Recruitment Specialist", "summary": "3 years of recruitment experience in the IT services industry.",
     "skills": ["Recruitment", "Candidate Sourcing", "Onboarding", "Excel", "Interview Coordination", "Applicant Tracking"],
     "experience": [("Recruitment Specialist", "Techhive Services", "Jan 2025", None, "Hired 120 IT professionals a year; ran campus drives in four cities."),
                    ("Recruitment Associate", "Techhive Services", "Oct 2023", "Dec 2024", "Sourced developers and coordinated interviews.")],
     "education": [("MBA in Human Resources", "Christ University", "2022")], "certs": [],
     "scr": "dropped", "hr": "good", "tech": None, "mt": None, "salary_lpa": 7, "notice_days": 60,
     "company": "Techhive Services", "achievement": "hired a hundred and twenty IT professionals in a year",
     "weakness": "I sometimes over-prepare for interviews, so I now keep a short checklist", "goal": "become a hiring manager's trusted partner",
     "project": "campus drives in four cities",
     "expected": ["hold_review"], "rationale": "the call ended early, so the evidence is incomplete: hold for evidence, not a rejection"},
]
