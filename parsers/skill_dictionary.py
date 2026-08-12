"""
Master Skill Dictionary (Day 9)

Every known skill, grouped by domain (tech / business / creative), with its
common synonyms/spelling variants and the Day 4 SkillObject.category it
maps to.

This is the single source of truth skill_extractor.py matches text against.
Adding a new skill means adding one entry here -- nothing else in the
extraction engine needs to change.
"""

# canonical_name: {"synonyms": [...], "group": "tech"|"business"|"creative", "category": <Day 4 SkillObject.category>}
SKILL_DICTIONARY = {
    # --- Tech: languages & frameworks ---
    "React.js": {"synonyms": ["react", "reactjs", "react.js", "react js"], "group": "tech", "category": "technical"},
    "Node.js": {"synonyms": ["node", "nodejs", "node.js", "node js"], "group": "tech", "category": "technical"},
    "Express.js": {"synonyms": ["express", "expressjs", "express.js"], "group": "tech", "category": "technical"},
    "Angular": {"synonyms": ["angularjs", "angular.js"], "group": "tech", "category": "technical"},
    "Vue.js": {"synonyms": ["vue", "vuejs", "vue.js"], "group": "tech", "category": "technical"},
    "MongoDB": {"synonyms": ["mongo db", "mongo", "mongodb"], "group": "tech", "category": "technical"},
    "PostgreSQL": {"synonyms": ["postgres", "postgre sql", "postgresql"], "group": "tech", "category": "technical"},
    "MySQL": {"synonyms": ["my sql", "mysql"], "group": "tech", "category": "technical"},
    "Python": {"synonyms": ["python3", "python 3"], "group": "tech", "category": "technical"},
    "JavaScript": {"synonyms": ["js", "java script", "javascript"], "group": "tech", "category": "technical"},
    "TypeScript": {"synonyms": ["ts", "typescript", "type script"], "group": "tech", "category": "technical"},
    "PHP": {"synonyms": ["php"], "group": "tech", "category": "technical"},
    "Java": {"synonyms": ["java"], "group": "tech", "category": "technical"},
    "PyTorch": {"synonyms": ["py torch", "pytorch"], "group": "tech", "category": "technical"},
    "Django": {"synonyms": ["django"], "group": "tech", "category": "technical"},
    "Flask": {"synonyms": ["flask"], "group": "tech", "category": "technical"},
    "Spring Boot": {"synonyms": ["spring boot", "springboot", "spring"], "group": "tech", "category": "technical"},
    "TensorFlow": {"synonyms": ["tensor flow", "tensorflow"], "group": "tech", "category": "technical"},
    "scikit-learn": {"synonyms": ["sklearn", "scikit learn", "scikit-learn"], "group": "tech", "category": "technical"},
    "Pandas": {"synonyms": ["pandas"], "group": "tech", "category": "technical"},
    "SQL": {"synonyms": ["sql"], "group": "tech", "category": "technical"},
    "REST APIs": {"synonyms": ["rest api", "rest apis", "restful api", "rest api design"], "group": "tech", "category": "technical"},
    "GraphQL": {"synonyms": ["graph ql", "graphql"], "group": "tech", "category": "technical"},
    "HTML": {"synonyms": ["html", "html5"], "group": "tech", "category": "technical"},
    "CSS": {"synonyms": ["css", "css3"], "group": "tech", "category": "technical"},
    "Next.js": {"synonyms": ["nextjs", "next.js", "next js"], "group": "tech", "category": "technical"},
    "jQuery": {"synonyms": ["jquery", "j query"], "group": "tech", "category": "technical"},
    "C++": {"synonyms": ["c++", "cpp"], "group": "tech", "category": "technical"},
    "Jenkins": {"synonyms": ["jenkins"], "group": "tech", "category": "tool"},
    "Jira": {"synonyms": ["jira"], "group": "tech", "category": "tool"},
    "Agile": {"synonyms": ["agile", "agile methodology"], "group": "tech", "category": "domain"},
    "Scrum": {"synonyms": ["scrum"], "group": "tech", "category": "domain"},
    "Linux": {"synonyms": ["linux"], "group": "tech", "category": "tool"},

    # --- Tech: infra & tools ---
    "Docker": {"synonyms": ["docker"], "group": "tech", "category": "tool"},
    "Kubernetes": {"synonyms": ["k8s", "kubernetes"], "group": "tech", "category": "tool"},
    "AWS": {"synonyms": ["amazon web services", "aws"], "group": "tech", "category": "tool"},
    "GCP": {"synonyms": ["google cloud", "google cloud platform", "gcp"], "group": "tech", "category": "tool"},
    "Azure": {"synonyms": ["microsoft azure", "azure"], "group": "tech", "category": "tool"},
    "Terraform": {"synonyms": ["terraform"], "group": "tech", "category": "tool"},
    "Git": {"synonyms": ["git"], "group": "tech", "category": "tool"},
    "GitHub": {"synonyms": ["github", "git hub"], "group": "tech", "category": "tool"},
    "CI/CD": {"synonyms": ["ci cd", "ci/cd", "continuous integration"], "group": "tech", "category": "tool"},
    "Redis": {"synonyms": ["redis"], "group": "tech", "category": "tool"},
    "Celery": {"synonyms": ["celery"], "group": "tech", "category": "tool"},
    "Power BI": {"synonyms": ["powerbi", "power-bi", "power bi"], "group": "tech", "category": "tool"},
    "Excel": {"synonyms": ["ms excel", "microsoft excel", "excel"], "group": "tech", "category": "tool"},
    "MLflow": {"synonyms": ["ml flow", "mlflow"], "group": "tech", "category": "tool"},
    "AutoCAD": {"synonyms": ["auto cad", "autocad"], "group": "tech", "category": "tool"},
    "SolidWorks": {"synonyms": ["solid works", "solidworks"], "group": "tech", "category": "tool"},

    # --- Business ---
    "Salesforce": {"synonyms": ["salesforce crm", "salesforce"], "group": "business", "category": "tool"},
    "Cold Calling": {"synonyms": ["cold calling", "cold call"], "group": "business", "category": "soft"},
    "Negotiation": {"synonyms": ["negotiation", "negotiation skills"], "group": "business", "category": "soft"},
    "Lead Generation": {"synonyms": ["lead generation", "lead gen"], "group": "business", "category": "soft"},
    "CRM": {"synonyms": ["crm", "customer relationship management"], "group": "business", "category": "tool"},
    "GST Filing": {"synonyms": ["gst filing", "gst"], "group": "business", "category": "domain"},
    "Tally ERP": {"synonyms": ["tally", "tally erp"], "group": "business", "category": "tool"},
    "Financial Reporting": {"synonyms": ["financial reporting"], "group": "business", "category": "domain"},
    "Recruitment": {"synonyms": ["recruitment", "hiring", "talent acquisition"], "group": "business", "category": "domain"},
    "Onboarding": {"synonyms": ["onboarding"], "group": "business", "category": "domain"},
    "SEO": {"synonyms": ["seo", "search engine optimization"], "group": "business", "category": "domain"},
    "Google Ads": {"synonyms": ["google ads", "adwords", "google adwords"], "group": "business", "category": "tool"},
    "Google Analytics": {"synonyms": ["google analytics", "ga"], "group": "business", "category": "tool"},
    "Email Marketing": {"synonyms": ["email marketing"], "group": "business", "category": "domain"},

    # --- Creative ---
    "Figma": {"synonyms": ["figma"], "group": "creative", "category": "tool"},
    "Adobe XD": {"synonyms": ["adobe xd", "adobexd"], "group": "creative", "category": "tool"},
    "Sketch": {"synonyms": ["sketch"], "group": "creative", "category": "tool"},
    "Prototyping": {"synonyms": ["prototyping"], "group": "creative", "category": "domain"},
    "User Research": {"synonyms": ["user research"], "group": "creative", "category": "domain"},
    "Design Systems": {"synonyms": ["design systems", "design system"], "group": "creative", "category": "domain"},
    "Copywriting": {"synonyms": ["copywriting"], "group": "creative", "category": "domain"},
    "Content Strategy": {"synonyms": ["content strategy"], "group": "creative", "category": "domain"},
    "WordPress": {"synonyms": ["wordpress", "word press"], "group": "creative", "category": "tool"},
}

# Named skill stacks that imply a fixed set of underlying skills.
SKILL_STACKS = {
    "MERN": ["MongoDB", "Express.js", "React.js", "Node.js"],
    "MEAN": ["MongoDB", "Express.js", "Angular", "Node.js"],
    "MEVN": ["MongoDB", "Express.js", "Vue.js", "Node.js"],
}
