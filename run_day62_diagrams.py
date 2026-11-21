"""Day 62: draws the four handbook diagrams into docs/diagrams/ (matplotlib).  Run: python run_day62_diagrams.py"""
import os, sys
os.chdir(os.path.dirname(os.path.abspath(__file__)))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
OUT="docs/diagrams/"
NAVY="#1F3A5F"; BLUE="#DCE8F5"; GREY="#F2F2F2"; GREEN="#DDF0E1"; AMBER="#FFF1D6"; RED="#F8DCDC"

def box(ax,x,y,w,h,text,fc=BLUE,ec=NAVY,fs=9,bold=False,ls="-"):
    ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle="round,pad=0.02,rounding_size=0.08",fc=fc,ec=ec,lw=1.2,ls=ls))
    ax.text(x+w/2,y+h/2,text,ha="center",va="center",fontsize=fs,fontweight="bold" if bold else "normal",color="#111",wrap=True)
def arrow(ax,x1,y1,x2,y2,text=None,ls="-"):
    ax.add_patch(FancyArrowPatch((x1,y1),(x2,y2),arrowstyle="-|>",mutation_scale=12,lw=1.2,color=NAVY,ls=ls))
    if text: ax.text((x1+x2)/2,(y1+y2)/2+0.12,text,ha="center",fontsize=7.5,color="#333")

# 1 ---------------- architecture
fig,ax=plt.subplots(figsize=(11,7.2)); ax.set_xlim(0,11); ax.set_ylim(0,7.2); ax.axis("off")
ax.text(5.5,6.95,"Zecpath AI layer: where it sits",ha="center",fontsize=13,fontweight="bold",color=NAVY)
box(ax,0.3,5.6,10.4,0.9,"Zecpath backend and frontend (NOT in this repository): accounts, job posting, scheduling, telephony, video, email, payments, database",GREY,ls="--",fs=9)
box(ax,0.3,4.5,10.4,0.8,"AI gateway (PLANNED: Day 59 contract, not built): authentication, scopes, schema checks, idempotency, queue for async jobs",AMBER,ls="--",fs=9)
arrow(ax,5.5,5.6,5.5,5.3); arrow(ax,5.5,4.5,5.5,4.2)
ax.text(5.5,4.28,"",fontsize=7)
ax.add_patch(FancyBboxPatch((0.3,0.9),10.4,3.25,boxstyle="round,pad=0.02,rounding_size=0.1",fc="white",ec=NAVY,lw=1.8))
ax.text(0.5,3.9,"THIS REPOSITORY: five stateless services behind run(payload), all subclasses of BaseAIService",fontsize=9.5,fontweight="bold",color=NAVY)
sv=[("ATS service\nresume x job\n-> score, zone",0.5),("Resume parsing\nPDF/DOCX\n-> text, skills",2.6),("Screening\ncall turns\n-> call score",4.7),("Interview\nHR / technical\n-> scores",6.8),("Decision\nround scores\n-> recommendation",8.9)]
for t,x in sv: box(ax,x,2.55,1.75,1.05,t,BLUE,fs=8.3)
box(ax,0.5,1.5,9.9,0.75,"Engines in parsers/: extraction, ATS formula, screening, HR, technical, machine test,\naggregation, recommendation, reports",GREEN,fs=8.6)
box(ax,0.5,1.05,9.9,0.4,"Shared: utils/ (base service, config, logger, cache, warm-up)  |  governance: audit, retention, consent, access rules  |  observability",GREY,fs=8)
box(ax,0.3,0.05,10.4,0.6,"Data reached through the backend: resume_store, job_store, transcript_store, report_store, audit_store\n(the AI layer itself never touches a database)",GREY,ls="--",fs=8.6)
arrow(ax,5.5,0.65,5.5,0.9)
fig.savefig(OUT+"day62_architecture.png",dpi=160,bbox_inches="tight"); plt.close(fig)

# 2 ---------------- candidate workflow
fig,ax=plt.subplots(figsize=(11,6.4)); ax.set_xlim(0,11); ax.set_ylim(0,6.4); ax.axis("off")
ax.text(5.5,6.15,"Candidate journey through the AI layer (the order the real engines run in)",ha="center",fontsize=12.5,fontweight="bold",color=NAVY)
X=[0.2,2.4,4.6,6.8,9.0]
r1=[("Resume file\n(PDF/DOCX)",GREY),("Extract text\nand sections",BLUE),("ATS score\n+ zone",BLUE),("Eligibility\n(hard gates)",BLUE),("Screening call\nscore",BLUE)]
r2=[("HR interview\nscore",BLUE),("Technical\ninterview score",BLUE),("Machine test\nscore",BLUE),("Cross-round\nHiring Fit Score",GREEN),("Recommendation\n+ confidence",GREEN)]
for i,(t,c) in enumerate(r1): box(ax,X[i],4.6,1.7,1.0,t,c,fs=8.6)
for i,(t,c) in enumerate(r2): box(ax,X[i],2.8,1.7,1.0,t,c,fs=8.6)
for i in range(4): arrow(ax,X[i]+1.7,5.1,X[i+1],5.1); arrow(ax,X[i]+1.7,3.3,X[i+1],3.3)
arrow(ax,9.85,4.6,9.85,4.2); ax.plot([9.85,1.05],[4.2,4.2],color=NAVY,lw=1.2); arrow(ax,1.05,4.2,1.05,3.8)
box(ax,0.2,1.35,3.3,0.95,"Technical roles use the technical and\nmachine-test rounds. Non-technical\nroles: those two are not applicable.",AMBER,fs=8,ls="--")
box(ax,3.75,1.35,3.5,0.95,"A round that has not happened gives a\nPROVISIONAL score and 'hold for evidence'.\nA missing score is never counted as zero.",AMBER,fs=8,ls="--")
box(ax,7.5,1.35,3.3,0.95,"A rejection is only ever a recommendation:\na named person must confirm it.",RED,fs=8.2,ls="--")
box(ax,0.2,0.2,10.6,0.7,"After scoring: recruiter report (hiring_report_generator), candidate-facing notice, decision audit entry (audit_trail + decision_audit)",GREEN,fs=8.4)
fig.savefig(OUT+"day62_candidate_workflow.png",dpi=160,bbox_inches="tight"); plt.close(fig)

# 3 ---------------- scoring flow
fig,ax=plt.subplots(figsize=(11,6.2)); ax.set_xlim(0,11); ax.set_ylim(0,6.2); ax.axis("off")
ax.text(5.5,5.95,"How a score becomes a recommendation",ha="center",fontsize=12.5,fontweight="bold",color=NAVY)
box(ax,0.2,4.5,2.4,1.0,"Round scores (0-100 each)\nATS raw by default;\nzone-aligned is opt-in",BLUE,fs=8.6)
box(ax,3.1,4.5,2.4,1.0,"Role weights\ntechnical or\nnon-technical",BLUE,fs=8.6)
box(ax,6.0,4.5,2.4,1.0,"Fresher adjustment\nATS x0.5,\nskill rounds x1.15",BLUE,fs=8.6)
box(ax,8.8,4.5,2.0,1.0,"Hiring Fit\nScore (%)",GREEN,fs=9,bold=True)
for x1,x2 in ((2.6,3.1),(5.5,6.0),(8.4,8.8)): arrow(ax,x1,5.0,x2,5.0)
box(ax,0.2,2.9,3.4,1.1,"Base band from the score:\n>= 70 selected, 50-70 hold, < 50 rejected",BLUE,fs=8.6)
box(ax,3.9,2.9,6.9,1.1,"Rules only move an outcome TOWARD review, never toward rejection:\nincomplete evidence -> hold  |  rejection with confidence below 50 -> hold\nblocks 'selected': a skill round below 40, integrity tag medium/high,\nborderline or disagreeing rounds, selection confidence below 55",AMBER,fs=8.2)
arrow(ax,9.8,4.5,2.0,4.0); arrow(ax,2.0,4.0,2.0,4.0)
box(ax,0.2,1.2,3.4,1.1,"Confidence (0-100): margin 35%,\ncoverage 25%, agreement 20%,\nstability 20%, x risk multiplier",BLUE,fs=8.3)
box(ax,3.9,1.2,3.3,1.1,"Outcome:\nselected | hold_review | rejected\n+ rule trace + reasons",GREEN,fs=8.4,bold=True)
box(ax,7.5,1.2,3.3,1.1,"rejected means\nhuman_confirmation_required = true\nand automated_action = none",RED,fs=8.4)
arrow(ax,3.6,3.45,3.9,3.45); arrow(ax,5.55,2.9,5.55,2.3); arrow(ax,7.2,1.75,7.5,1.75); arrow(ax,3.6,1.75,3.9,1.75)
ax.text(5.5,0.55,"Weights and thresholds are reasoned defaults, not calibrated against real hiring outcomes (no such data exists in this project).",ha="center",fontsize=8.2,style="italic",color="#444")
fig.savefig(OUT+"day62_scoring_flow.png",dpi=160,bbox_inches="tight"); plt.close(fig)

# 4 ---------------- request lifecycle (sequence-style)
fig,ax=plt.subplots(figsize=(11,5.6)); ax.set_xlim(0,11); ax.set_ylim(0,5.6); ax.axis("off")
ax.text(5.5,5.35,"One API call: what happens inside run(payload)",ha="center",fontsize=12.5,fontweight="bold",color=NAVY)
cols=[("Caller\n(backend)",1.0),("Gateway\n(planned)",3.2),("Service\n.run()",5.4),("Engine\n.process()",7.6),("Log events\n(observer)",9.8)]
for t,x in cols:
    box(ax,x-0.8,4.35,1.6,0.75,t,BLUE,fs=8.6); ax.plot([x,x],[0.3,4.35],color="#999",lw=0.9,ls=":")
msgs=[(1.0,3.2,3.9,"request + token"),(3.2,5.4,3.45,"schema-checked body"),(5.4,7.6,3.0,"validated payload"),(7.6,5.4,2.55,"result dict"),(5.4,9.8,2.1,"observer: log events (numbers and codes only)"),(5.4,3.2,1.65,"JSON-safe envelope (success or error)"),(3.2,1.0,1.2,"HTTP status + envelope")]
for x1,x2,y,t in msgs: arrow(ax,x1,y,x2,y,t)
ax.text(5.5,0.55,"run() never raises: an unexpected exception becomes 'internal_error' with a generic message; the full trace stays in the log.",ha="center",fontsize=8.2,style="italic",color="#444")
fig.savefig(OUT+"day62_request_lifecycle.png",dpi=160,bbox_inches="tight"); plt.close(fig)
print("ok")
