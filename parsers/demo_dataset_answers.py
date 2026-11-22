"""
Demo dataset content (Day 63), part 2: what each fictional candidate SAYS and DOES in every round

Part 1 (`demo_dataset_content.py`) says who the candidates are. This part turns a persona into the words and artefacts the engines consume:

  * screening answers      one short answer per screening question, in the order the system asks them
  * HR interview answers   six answers, in six quality levels (excellent ... limited English)
  * technical answers      keyed by domain and experience tier, in three quality levels (strong / ok / weak)
  * machine-test attempts  two small Python tasks; each candidate's code snapshots are really executed against the task's test cases when
                           the dataset is built, so the recorded pass / fail results are the code's real behaviour, not typed by hand

TEMPLATES, NOT TRANSCRIPTS. Answers are assembled from a persona's own facts (company, achievement, weakness, goal, project) and a quality
level, so a candidate's resume, call and interviews tell one consistent story (except where a persona is meant to contradict itself).
The text is deliberately plain: it is test data for a scoring layer, not a model of how people talk.

Input contract:  a persona dict (see demo_dataset_content.PERSONAS) and, for machine tests, the task definitions below.
Output contract: plain dicts and lists, JSON-serialisable.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

SCREENING_ORDER = ["introduction", "education", "experience", "skills", "location", "salary", "notice_period"]   # = the question bank order

# What each job family is about, used to colour the HR answers.
JOB_FLAVOUR: Dict[str, Dict[str, str]] = {
    "JOB-01": {"enjoy": "building features end to end", "strength": "breaking big problems into small testable steps", "lesson": "performance and reliability", "junior": "junior developer"},
    "JOB-02": {"enjoy": "building reliable services", "strength": "tracing a problem down to its real cause", "lesson": "data and performance", "junior": "associate developer"},
    "JOB-03": {"enjoy": "making deployments boring and reliable", "strength": "automating repeated work safely", "lesson": "reliability and rollback", "junior": "systems engineer"},
    "JOB-04": {"enjoy": "building long-term client relationships", "strength": "listening first and then framing the value clearly", "lesson": "qualifying leads", "junior": "sales associate"},
    "JOB-05": {"enjoy": "turning messy problems into clear flows", "strength": "testing ideas early with real users", "lesson": "user research", "junior": "junior designer"},
    "JOB-06": {"enjoy": "matching people to the right roles", "strength": "staying organised across many open requisitions", "lesson": "candidate experience", "junior": "HR trainee"},
}


def _years_text(years: float) -> str:
    """'4.5 years', '8 years'. Digits, not words: the screening engine reads numbers reliably but reads 'six months' as 6 years."""
    value = int(years) if float(years).is_integer() else years
    return f"{value} years"


def _first(name: str) -> str:
    return name.split()[0]


def _skills(p: Dict[str, Any], n: int) -> str:
    items = p["skills"][:n]
    return ", ".join(items[:-1]) + " and " + items[-1] if len(items) > 1 else items[0]


# --------------------------------------------------------------------------------------------------------------------------- screening
def screening_answers(p: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    """The seven screening answers (with a speech-recognition confidence each) and the short re-ask answers.
    A 'vague' candidate dodges the question; when the system asks again the candidate gives the plain version."""
    level = p["scr"]
    confidence = p.get("scr_confidence", 0.93)
    claimed = p.get("claims_years") or p["years"]
    degree, institute, year = p["education"][0]
    years_phrase = _years_text(claimed) if claimed >= 1 or claimed == 0.5 else "no full-time experience, only a short internship"
    if p["years"] == 0.5:
        years_phrase = "0.5 years"
    if p["years"] == 0.0:
        years_phrase = "0 years of full-time experience"
    designation = p["designation"]
    strong = {
        "introduction": f"Hi, I'm {p['name']}, a {designation} based in {p['city']}. I recently worked on {p['project']}.",
        "education": f"I completed my {degree} from {institute} in {year}.",
        "experience": f"I have {years_phrase} of experience, and I am currently working at {p['company']}.",
        "skills": f"My main skills are {_skills(p, 6)}.",
        "location": f"I am currently based in {p['city']}.",
        "salary": f"I'm expecting around {p['salary_lpa']} lakhs per annum, and I'm open to discussion.",
        "notice_period": f"My notice period is {p['notice_days']} days.",
    }
    ok = {
        "introduction": f"Hello, my name is {p['name']} and I work as a {designation}.",
        "education": f"I did my {degree}, in {year}.",
        "experience": f"I have around {years_phrase} of experience.",
        "skills": f"I mainly work with {_skills(p, 3)}.",
        "location": f"I am in {p['city']}.",
        "salary": f"Around {p['salary_lpa']} lakhs per annum.",
        "notice_period": f"{p['notice_days']} days notice.",
    }
    vague = {
        "introduction": f"Yes, I am {_first(p['name'])}. I do some work in this field, mostly whatever the team needs.",
        "education": "I studied in college and completed my degree.",
        "experience": "I have quite some experience in this line, a few years.",
        "skills": "I am a fast learner and a hard worker, I can learn anything quickly.",
        "location": "I can relocate anywhere, it is no problem for me.",
        "salary": "As per company standards, whatever is fair.",
        "notice_period": "I can join soon, it is flexible.",
    }
    bank = {"strong": strong, "ok": ok, "vague": vague, "dropped": strong}[level]
    order = SCREENING_ORDER[:3] if level == "dropped" else SCREENING_ORDER
    answers = [{"text": bank[cat], "confidence": confidence} for cat in order]
    reask = {cat: ok[cat] for cat in SCREENING_ORDER} if level == "vague" else {}
    return answers, reask


# --------------------------------------------------------------------------------------------------------------------------- HR interview
HR_QUESTIONS = ["self_introduction", "career_journey", "strengths_weaknesses", "teamwork_culture_fit", "career_goals", "availability_commitment"]


def hr_answers(p: Dict[str, Any]) -> List[str]:
    """Six HR answers for the persona's quality level."""
    level = p["hr"]
    f = JOB_FLAVOUR[p["job"]]
    years = _years_text(p["years"]) if p["years"] >= 1 else "very little experience so far"
    base = {
        "name": p["name"], "des": p["designation"], "years": years, "company": p["company"], "ach": p["achievement"], "weak": p["weakness"],
        "goal": p["goal"], "proj": p["project"], "days": p["notice_days"], "city": p["city"], "enjoy": f["enjoy"], "strength": f["strength"],
        "lesson": f["lesson"], "junior": f["junior"],
    }
    templates: Dict[str, List[str]] = {
        "excellent": [
            "I'm a {des} with {years} of experience. At {company} I {ach}. I enjoy {enjoy}, and I like owning an outcome from the first idea until it is running well.",
            "I started as a {junior} and took on more responsibility each year. The work that taught me most was {proj}, because it made me think carefully about {lesson} and about the people who depend on what I build.",
            "My main strength is {strength}. A weakness I have worked on: {weak}. That habit has made my work calmer and my teams more predictable.",
            "I work best in teams that share feedback openly. When we disagreed on priorities I suggested we write down the options and their trade-offs, we discussed them together, and we agreed on a plan that we delivered on time.",
            "In the next two to three years I want to {goal}, while staying close to the day-to-day work and continuing to learn from people more experienced than me.",
            "My notice period is {days} days, I am comfortable with the location and the working model, and I am looking for a role where I can stay for several years and make a real contribution.",
        ],
        "good": [
            "I'm a {des} with {years} of experience. At {company} I {ach}. I enjoy {enjoy}.",
            "I began as a {junior} and grew into my current role. A project I learned a lot from was {proj}, and it taught me about {lesson}.",
            "I am good at {strength}. One thing I am improving: {weak}.",
            "I like working in a team and asking for feedback. Once we had a disagreement about priorities, so we listed the options and chose one together.",
            "In a few years I would like to {goal}.",
            "My notice period is {days} days and I am fine with the location. I am looking for a long-term role.",
        ],
        "average": [
            "I am a {des} with {years} of experience. I work at {company} and I do my tasks sincerely.",
            "I have worked in this field for some time and done several projects, such as {proj}.",
            "I am hard working and sincere. I want to improve my skills further.",
            "I get along with everyone in the team and I try to help others when needed.",
            "I want to grow in my career and take more responsibility in the future.",
            "My notice period is {days} days. I am ready to join if the offer is good.",
        ],
        "weak": [
            "I am a hard working person. I have done many things.",
            "I worked in some places and did different work.",
            "I am a perfectionist and I work too hard.",
            "I do not have any problem with anyone.",
            "I want to be at the top one day.",
            "I can join whenever.",
        ],
        "nervous": [
            "Um, thank you. So, I'm a {des}, and I have {years} of experience, I think. At {company} I {ach}. Sorry, I get a little nervous in interviews.",
            "Um, I started as a {junior}, and then, I think, I grew into my role. The project I learned most from was {proj}, because it taught me about {lesson}.",
            "My strength is, I would say, {strength}. A weakness, um, {weak}.",
            "I work well with a team, I think. Once there was a disagreement, and we, um, listed the options and decided together, so that worked well.",
            "I would like to, um, {goal}, in a few years, if I keep learning.",
            "My notice period is {days} days, and I am, I think, flexible about the rest. I would like a long-term role.",
        ],
        "limited_english": [
            "I am {name}. I am working as {des} from {years}. In my company {company} I {ach}.",
            "First I started as {junior}, then I learn many things and now I am {des}. I did {proj}.",
            "My strength is {strength}. My weakness is {weak}.",
            "I like to work in team. If problem is there, we sit together and solve it.",
            "In future I want to {goal}. I will work hard for this.",
            "My notice period is {days} days. I can join after that and I want long time job.",
        ],
    }
    return [t.format(**base) for t in templates[level]]


# --------------------------------------------------------------------------------------------------------------------------- technical interview
_DECISIONS = {
    "mern": "React for the front end, Node.js and Express for the API, and MongoDB with indexes designed around our main queries",
    "java": "Spring Boot with PostgreSQL, caching hot reads in Redis, and integration tests around the main flows",
    "devops": "Terraform for the infrastructure, Kubernetes for deployment, and a Jenkins pipeline with automated tests and rollbacks",
}

# (domain, tier) -> question id suffix -> {strong, ok, weak}
TECH_BANK: Dict[Tuple[str, str], Dict[str, Dict[str, str]]] = {
    ("mern", "basics"): {
        "c01": {
            "strong": "Props are inputs passed from a parent component to a child and they are read-only, so the child cannot change them. State is data that a component owns and manages itself, and updating it with the useState hook triggers a re-render. A common pattern is lifting state up to a parent and passing it down as props so that sibling components share the same data.",
            "ok": "Props come from the parent component and state lives inside the component. State can change and props cannot.",
            "weak": "They are both used to store data in React. I do not remember the exact difference.",
        },
        "c02": {
            "strong": "Middleware in Express are functions that run between the request and the response, and they receive req, res and the next function. They are used for cross-cutting work such as logging, parsing JSON bodies, authentication, CORS and error handling. The order in which you register them matters, and each one must either call next or end the response.",
            "ok": "Middleware is a function in Express that runs before the route handler, for example to check authentication.",
            "weak": "It is something in Express that sits in the middle. I have used it but I am not sure how it works.",
        },
        "s01": {
            "strong": "I would first use the React DevTools profiler to confirm which components re-render and why. Typical causes are the search state living in a common parent so every keystroke re-renders the list, or new object and function props created on each render. I would move the search state into its own component or debounce the input, wrap the list in React.memo, stabilise props with useMemo and useCallback, and make sure the list items have stable keys. Then I would measure again to confirm the fix.",
            "ok": "I would check whether the state is in the parent component and use memo so the list does not re-render again and again.",
            "weak": "I would reload the page and try to see what is wrong, maybe use a different library.",
        },
    },
    ("mern", "intermediate"): {
        "c01": {
            "strong": "Node.js runs JavaScript on a single thread with an event loop. Asynchronous work such as file and network I/O is handed to the operating system or the libuv thread pool, and when it finishes its callback is queued. The event loop picks callbacks up in phases, timers then I/O callbacks then setImmediate, and between phases it drains the microtask queue where promises and process.nextTick run. Heavy CPU work blocks the loop and delays every request, so it should move to worker threads or a separate service.",
            "ok": "Node is single threaded and uses callbacks and promises. The event loop takes finished tasks from the queue so the main thread does not block.",
            "weak": "It runs things one by one. I am not sure about the details.",
        },
        "c02": {
            "strong": "A MongoDB index is a B-tree structure that lets the database find documents without scanning the whole collection, so queries on an indexed field are much faster. Compound indexes help queries that filter and sort on several fields, where the field order matters. The trade-off is extra storage and slower writes, because every insert and update also updates the indexes, so I index the fields used in frequent queries and use explain to confirm that the index is really used.",
            "ok": "Indexes make queries faster because MongoDB does not scan every document, but too many indexes slow down writes.",
            "weak": "An index is like a key, it helps in searching. I do not know more than that.",
        },
        "s01": {
            "strong": "I would start with metrics and logs to see when the 504 errors happen: latency percentiles, CPU and memory, event loop lag and database connection pool usage. Common causes are slow MongoDB queries without indexes, blocking synchronous code in the event loop, an exhausted connection pool under load, or an upstream timeout shorter than the slowest request. I would check the load balancer and Express timeouts, reproduce the problem with a load test, profile the slow endpoints and then fix it, for example by adding indexes, caching, or moving heavy work to a queue.",
            "ok": "I would check the logs to see which API is slow, probably a database query, then add an index or increase the timeout.",
            "weak": "It works locally, so maybe the server is slow. I would restart the server.",
        },
    },
    ("mern", "advanced"): {
        "c01": {
            "strong": "I would keep state as local as possible and lift only what is truly shared. For server data I would use a data-fetching library such as React Query to handle caching and revalidation instead of copying it into a global store. Context is fine for low-frequency values like the theme or the current user, but it re-renders every consumer on change, so for frequently changing shared client state I would use Redux Toolkit or a lighter store such as Zustand with selectors. The trade-off is boilerplate and indirection against predictability, so I choose per use case and keep selectors memoised to avoid unnecessary re-renders.",
            "ok": "I would use Redux for global state and Context for small things, and keep the components small.",
            "weak": "I would keep one global state file and pass it to all the components.",
        },
        "c02": {
            "strong": "MongoDB scales horizontally through sharding: data is split into chunks by a shard key and distributed across shards, with mongos routers directing queries and config servers holding the metadata. The shard key choice is critical, because a monotonically increasing key creates a hot shard, while a high-cardinality or hashed key balances writes. The trade-offs are operational complexity, scatter-gather queries that do not include the shard key, and the difficulty of changing the key later, so I would shard only when a single replica set can no longer cope.",
            "ok": "Sharding splits the data over many servers using a shard key. It helps to scale but the shard key must be chosen well.",
            "weak": "Mongo can be scaled by adding more servers. I have not done sharding myself.",
        },
        "s01": {
            "strong": "I would use WebSockets, for example Socket.IO, for low-latency two-way updates, with Node.js servers behind a load balancer using sticky sessions or a Redis pub/sub adapter so events reach every instance. For concurrent edits I would use operational transformation or a CRDT library such as Yjs to merge changes without conflicts. Documents and version history would be stored in MongoDB with periodic snapshots, and presence kept in Redis. On the React side I would apply optimistic updates and batch changes. To scale to thousands of users I would shard by document, add rate limiting and monitoring, and plan for reconnection and offline edits.",
            "ok": "I would use WebSockets for real-time updates, store the document in MongoDB and use a library to handle conflicts.",
            "weak": "I would make a React page and refresh it again and again to see updates from other users.",
        },
    },
    ("java", "basics"): {
        "c01": {
            "strong": "An interface defines a contract of methods that a class promises to implement, and a class can implement many interfaces, while an abstract class can hold shared state and partial implementation but a class can extend only one. I use an interface when unrelated classes need the same capability, and an abstract class when closely related classes share code. Since Java 8 interfaces can also have default methods.",
            "ok": "An interface has only method declarations and a class can implement many, and an abstract class can have some implemented methods.",
            "weak": "Both are used for inheritance. I do not remember the exact difference.",
        },
        "c02": {
            "strong": "The static keyword means a member belongs to the class itself and not to any one instance, so it is shared by all objects and can be used without creating an object. Static methods cannot use instance variables directly, and common uses are constants, utility methods such as Math.max, and the main method. Static fields are loaded when the class is loaded, so they should be used carefully because shared mutable state is hard to test.",
            "ok": "Static members belong to the class and not to an object, so we can call them without creating an object.",
            "weak": "Static is used for the main method and for things that do not change.",
        },
        "s01": {
            "strong": "I would start with the stack trace in the logs to find the exact line that throws the exception, then work out which reference is null and why, for example a missing database result, an uninitialised field or a method that returns null. I would add logging around that code, try to reproduce it with the same input, and write a unit test that fails. The fix could be validating input, using Optional or returning an empty collection instead of null, and adding null checks where null is a valid value. Finally I would check for similar patterns elsewhere.",
            "ok": "I would read the stack trace to find the line, then add a null check and logs there.",
            "weak": "I would restart the server and see if it happens again.",
        },
    },
    ("java", "intermediate"): {
        "c01": {
            "strong": "The JVM garbage collector reclaims objects that are no longer reachable from GC roots such as thread stacks and static references. The heap is divided into generations: new objects start in the young generation, and those that survive several minor collections are promoted to the old generation, which is collected less often. Collectors such as G1 work in regions and aim for a pause-time target, while a full GC is expensive and causes stop-the-world pauses, so I watch the GC logs and tune the heap size and the collector when pauses become too long.",
            "ok": "The garbage collector removes objects that are not referenced any more from the heap. There is a young and an old generation.",
            "weak": "Java deletes unused things automatically. I do not know how it decides.",
        },
        "c02": {
            "strong": "The == operator compares references, so it is true only when both variables point to the same object, while equals compares logical equality as defined by the class. Strings are the classic example: two different String objects with the same text are not == but are equals. If you override equals you must also override hashCode so that objects behave correctly in a HashMap or HashSet.",
            "ok": "== compares the reference and equals compares the content of the objects.",
            "weak": "Both are used to compare. Equals is for strings.",
        },
        "s01": {
            "strong": "I would measure first rather than guess: check application metrics through Actuator and Micrometer, response-time percentiles, thread pool and connection pool usage, and GC behaviour. Then I would profile with a tool such as VisualVM or a flame graph and look at the slow SQL with query logs or explain plans, since N+1 queries and missing indexes are very common in JPA and Hibernate code. Fixes could be adding indexes, fetch joins or batching, caching hot reads in Redis, tuning the HikariCP connection pool and moving slow work to asynchronous processing. I would verify with a load test before and after.",
            "ok": "I would check the logs and the database queries, add indexes and caching, and check the CPU and memory.",
            "weak": "I would restart the application and increase the server size.",
        },
    },
    ("devops", "intermediate"): {
        "c01": {
            "strong": "A liveness probe tells Kubernetes whether a container is still healthy, and if it fails the kubelet restarts the container, which recovers from deadlocks. A readiness probe tells Kubernetes whether the pod is ready to receive traffic, and if it fails the pod is removed from the service endpoints but not restarted. Both matter: readiness avoids sending requests to a pod that is starting or overloaded, liveness recovers stuck processes, and a startup probe helps slow-starting applications. A badly configured liveness probe can cause restart loops.",
            "ok": "Liveness checks if the container is alive and restarts it, and readiness checks if it can take traffic.",
            "weak": "They are health checks in Kubernetes, both are almost the same.",
        },
        "c02": {
            "strong": "Terraform is a declarative infrastructure-as-code tool used to provision resources such as networks, clusters and databases, tracking them in a state file and planning changes before applying them. Ansible is a configuration-management tool that configures what runs on the machines, installing packages and managing files and services, usually agentless over SSH. Terraform favours immutable infrastructure and creating resources, Ansible is more procedural about configuring them, and many teams use both together.",
            "ok": "Terraform creates the infrastructure and Ansible configures the servers after they are created.",
            "weak": "Both are automation tools. Terraform is for cloud.",
        },
        "s01": {
            "strong": "I would compare the artifacts and the environments: check that the same container image digest is deployed, and look for differences in environment variables, configuration, secrets, dependency versions and infrastructure such as the operating system, network policies or resource limits. I would check the logs and metrics in production, reproduce the issue in a staging environment that mirrors production, and look at data differences and feature flags. To prevent it I would build once and promote the same artifact, keep configuration in version control, and add smoke tests and monitoring after each deployment.",
            "ok": "I would check the configuration and the environment variables between CI and production, and look at the logs.",
            "weak": "Maybe the production server is different. I would ask the developers to check their code.",
        },
    },
}


def technical_answers(p: Dict[str, Any], domain: str, tier: str, question_suffixes: List[str]) -> Optional[List[str]]:
    """Answers for one technical session in the order the questions are asked: introduction, experience, then the tier's three questions.
    Returns None if the persona has no technical round."""
    level = p.get("tech")
    if level is None:
        return None
    years = _years_text(p["years"]) if p["years"] >= 1 else "less than a year"
    skills = _skills(p, 4)
    if level == "strong":
        intro = f"I'm a {p['designation']} with {years} of experience. Recently at {p['company']} I {p['achievement']}. Day to day I work with {skills}."
        exp = (f"A project I owned end to end was {p['project']}. I chose {_DECISIONS[domain]}, because it matched our access patterns and kept the system simple to run. "
               "I also handled testing, deployment and monitoring myself, and I learned to watch performance and failures from the start.")
    elif level == "ok":
        intro = f"I work as a {p['designation']} and I have {years} of experience with {_skills(p, 3)}."
        exp = f"I worked on {p['project']}. I mostly wrote features and fixed bugs, and I used {_skills(p, 3)}."
    else:
        intro = "I do development work, mostly small tasks given by my team."
        exp = "I worked on some projects, using the technologies the team used. I do not remember all the details."
    bank = TECH_BANK[(domain, tier)]
    return [intro, exp] + [bank[s][level] for s in question_suffixes]


# --------------------------------------------------------------------------------------------------------------------------- machine test
# Two small Python tasks. `cases` are (case_id, visible, input args, expected output). Hidden cases are never shown to the candidate.
TASKS: List[Dict[str, Any]] = [
    {"task_id": "MT-A", "task_type": "coding", "title": "Top N words", "difficulty": "basics", "time_limit_seconds": 1200, "function": "top_n_words",
     "reference_runtime_ms": 4.0,
     "cases": [("A-v1", True, ["the cat and the hat", 1], ["the"]),
               ("A-v2", True, ["a b a c b a", 2], ["a", "b"]),
               ("A-h1", False, ["Hello, hello! World.", 1], ["hello"]),
               ("A-h2", False, ["", 3], []),
               ("A-h3", False, ["b a b a c", 2], ["a", "b"]),
               ("A-h4", False, ["x y z", 5], ["x", "y", "z"])]},
    {"task_id": "MT-B", "task_type": "coding", "title": "Merge intervals", "difficulty": "intermediate", "time_limit_seconds": 1800, "function": "merge_intervals",
     "reference_runtime_ms": 3.0,
     "cases": [("B-v1", True, [[[1, 3], [2, 6], [8, 10]]], [[1, 6], [8, 10]]),
               ("B-v2", True, [[[1, 4], [4, 5]]], [[1, 5]]),
               ("B-h1", False, [[]], []),
               ("B-h2", False, [[[5, 6], [1, 2]]], [[1, 2], [5, 6]]),
               ("B-h3", False, [[[1, 10], [2, 3]]], [[1, 10]]),
               ("B-h4", False, [[[1, 2]]], [[1, 2]]),
               ("B-h5", False, [[[1, 5], [2, 3], [4, 8]]], [[1, 8]])]},
]

STUB = {"MT-A": "def top_n_words(text, n):\n    pass\n", "MT-B": "def merge_intervals(intervals):\n    pass\n"}

CODE: Dict[str, Dict[str, str]] = {
    "MT-A": {
        "strong": '''import re
from collections import Counter


def top_n_words(text, n):
    words = re.findall(r"[a-z']+", text.lower())
    counts = Counter(words)
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [word for word, _ in ordered[:n]]
''',
        "partial": '''def top_n_words(text, n):
    counts = {}
    for w in text.split():
        counts[w] = counts.get(w, 0) + 1
    ordered = sorted(counts, key=lambda w: counts[w], reverse=True)
    return ordered[:n]
''',
        "slow": '''import re


def top_n_words(text, n):
    words = re.findall(r"[a-z']+", text.lower())
    unique = []
    for w in words:
        if w not in unique:
            unique.append(w)
    unique.sort(key=lambda w: (-words.count(w), w))
    return unique[:n]
''',
        "overfit": '''def top_n_words(text, n):
    if text == "the cat and the hat":
        return ["the"]
    if text == "a b a c b a":
        return ["a", "b"]
    return []
''',
        "weak": '''def top_n_words(text, n)
    return text.split()[:n]
''',
    },
    "MT-B": {
        "strong": '''def merge_intervals(intervals):
    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged
''',
        "partial": '''def merge_intervals(intervals):
    merged = []
    for start, end in intervals:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = end
        else:
            merged.append([start, end])
    return merged
''',
        "slow": '''def merge_intervals(intervals):
    items = [list(i) for i in intervals]
    changed = True
    while changed:
        changed = False
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                a, b = items[i], items[j]
                if a[0] <= b[1] and b[0] <= a[1]:
                    items[i] = [min(a[0], b[0]), max(a[1], b[1])]
                    del items[j]
                    changed = True
                    break
            if changed:
                break
    return sorted(items)
''',
        "overfit": '''def merge_intervals(intervals):
    if intervals == [[1, 3], [2, 6], [8, 10]]:
        return [[1, 6], [8, 10]]
    if intervals == [[1, 4], [4, 5]]:
        return [[1, 5]]
    return intervals
''',
        "weak": '''def merge_intervals(intervals):
    result = []
    for i in intervals
        result.append(i)
    return result
''',
    },
}

# How the attempt unfolds, as fractions of the task's time limit: (snapshot times, finishing time, runtime multiplier vs the reference solution)
SHAPES: Dict[str, Dict[str, Any]] = {
    "strong": {"path": ["stub", "partial", "strong"], "finish": 0.42, "runtime": 1.1},
    "partial": {"path": ["stub", "partial"], "finish": 0.85, "runtime": 1.2},
    "slow": {"path": ["stub", "slow"], "finish": 0.70, "runtime": 7.5},
    "overfit": {"path": ["stub", "overfit"], "finish": 0.28, "runtime": 0.6},
    "weak": {"path": ["stub", "weak"], "finish": 1.0, "runtime": 1.0},
}
