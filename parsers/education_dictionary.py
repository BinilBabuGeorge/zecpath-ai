"""
Education & Certification Dictionaries (originally Day 11)
"""

DEGREE_DICTIONARY = {
    "B.Tech": {"synonyms": ["btech", "b.tech", "b tech", "bachelor of technology"], "level": "Bachelor's"},
    "B.E.": {"synonyms": ["be", "b.e.", "b e", "bachelor of engineering"], "level": "Bachelor's"},
    "B.Sc": {"synonyms": ["bsc", "b.sc", "b sc", "bachelor of science"], "level": "Bachelor's"},
    "B.Com": {"synonyms": ["bcom", "b.com", "b com", "bachelor of commerce"], "level": "Bachelor's"},
    "B.A.": {"synonyms": ["ba", "b.a.", "b a", "bachelor of arts"], "level": "Bachelor's"},
    "BBA": {"synonyms": ["bba", "b.b.a.", "bachelor of business administration"], "level": "Bachelor's"},
    "BCA": {"synonyms": ["bca", "b.c.a.", "bachelor of computer applications"], "level": "Bachelor's"},
    "B.Des": {"synonyms": ["bdes", "b.des", "b des", "bachelor of design"], "level": "Bachelor's"},
    "LLB": {"synonyms": ["llb", "ll.b.", "bachelor of laws"], "level": "Bachelor's"},
    "MBA": {"synonyms": ["mba", "m.b.a.", "master of business administration"], "level": "Master's"},
    "M.Tech": {"synonyms": ["mtech", "m.tech", "m tech", "master of technology"], "level": "Master's"},
    "M.E.": {"synonyms": ["me", "m.e.", "master of engineering"], "level": "Master's"},
    "M.Sc": {"synonyms": ["msc", "m.sc", "m sc", "master of science"], "level": "Master's"},
    "M.Com": {"synonyms": ["mcom", "m.com", "master of commerce"], "level": "Master's"},
    "M.Des": {"synonyms": ["mdes", "m.des", "master of design"], "level": "Master's"},
    "MCA": {"synonyms": ["mca", "m.c.a.", "master of computer applications"], "level": "Master's"},
    "M.A.": {"synonyms": ["ma", "m.a.", "master of arts"], "level": "Master's"},
    "Ph.D": {"synonyms": ["phd", "ph.d", "ph.d.", "doctor of philosophy", "doctorate"], "level": "Doctorate"},
    "Diploma": {"synonyms": ["diploma"], "level": "Diploma"},
}

DEGREE_LEVEL_RANK = {"Diploma": 1, "Bachelor's": 2, "Master's": 3, "Doctorate": 4}

CERT_CATEGORY_KEYWORDS = {
    "Cloud/DevOps": ["aws", "azure", "gcp", "google cloud", "kubernetes", "docker", "cloud"],
    "Project Management": ["pmp", "scrum", "agile", "prince2", "csm"],
    "HR": ["shrm", "phr", "hr certified", "human resources"],
    "Sales/CRM": ["salesforce", "hubspot sales"],
    "Design/UX": ["ux design", "google ux", "adobe certified", "usability"],
    "Data/Analytics": ["data analytics", "tableau", "power bi", "data science"],
    "Finance/Accounting": ["tally", "cpa", "cfa", "gst practitioner"],
    "Software Development": ["mongodb certified", "oracle certified", "microsoft certified", "developer associate", "kubernetes application developer"],
    "Marketing": ["google ads", "content marketing", "google analytics", "digital marketing"],
}
