"""직무 필터링/분류, 시니어리티, 요구 경력 추출."""
from __future__ import annotations

import re

# 이게 제목에 있으면 제외 규칙과 무관하게 대상 직무 ("Software Engineer, Google Pay, Communications" 등)
_STRONG = re.compile(
    r"software (development |dev |engineering )?(engineer|developer|manager)|\bsde\b|\bswe\b|"
    r"(machine learning|\bml|\bai|deep learning|llm) (software )?(engineer|scientist|researcher)|"
    r"research (engineer|scientist)|applied scientist|member of technical staff",
    re.I,
)

# 제목에 이 중 하나가 있어야 대상 직무
_INCLUDE = re.compile(
    r"software|\bswe\b|\bsde\b|developer|programmer|researcher|"
    r"machine learning|\bml\b|\bmle\b|deep learning|\bllm|"
    r"\bai (engineer|research|scientist|infrastructure engineer|systems|software|platform)|"
    r"research (engineer|scientist)|applied scientist|member of technical staff|\bmts\b|"
    r"data (engineer|scientist)|site reliability|\bsre\b|devops|"
    r"(backend|back-end|frontend|front-end|full[- ]?stack|mobile|ios|android|infrastructure|platform|"
    r"distributed systems|security|firmware|embedded|compiler|kernel|gpu|cuda|inference|"
    r"performance|cloud|web|database|devtools?|production|robotics|autonomy|graphics|forward deployed|"
    r"privacy|search|ranking|recommendation|computer vision|speech|nlp)\s+(software\s+)?engineer",
    re.I,
)

# 제목에 이게 있으면 제외 (비엔지니어링/하드웨어 전용)
_EXCLUDE = re.compile(
    r"recruit|sourcer|sales|account (executive|manager)|business development|marketing|"
    r"counsel|attorney|legal|paralegal|finance|accountant|payroll|tax\b|"
    r"technician|mechanic|machinist|assembler|welder|inspector|buyer|"
    r"customer (success|support)|support (engineer|specialist)|technical support|"
    r"solutions? (architect|consultant|specialist)|pre-?sales|sales engineer|"
    r"program manager|project manager|product manager|product marketing|"
    r"designer|writer|editor|communications|policy|people partner|hr\b|"
    r"administrative|assistant|coordinator|executive assistant|"
    r"mechanical|electrical engineer|rf engineer|antenna|optical|thermal|structures|propulsion|"
    r"manufacturing|supply chain|yield|quality engineer|test technician|"
    r"retail|genius|specialist\b|facilities|construction|data center technician|"
    r"analyst\b",
    re.I,
)

TRACKS = [
    # (이름, 제목 정규식) — 위에서부터 먼저 매치되는 것
    ("Eng Manager", r"\b(engineering|software development|sw|software) manager\b|manager,? (software|engineering)|head of engineering|director.*engineering"),
    ("ML/AI Research", r"research (scientist|engineer)|applied scientist|researcher|\bresearch\b"),
    ("ML/AI Eng", r"machine learning|\bml\b|\bmle\b|\bai\b|deep learning|\bllm|inference|genai|generative|artificial intelligence|computer vision|\bnlp\b|speech|perception|model"),
    ("Data", r"data (engineer|scientist|platform|infrastructure)|analytics engineer"),
    ("Infra/SRE", r"site reliability|\bsre\b|devops|infrastructure|platform|cloud|distributed|storage|network|production engineer|reliability|kubernetes|compute"),
    ("Security", r"security|privacy|trust|safety|detection"),
    ("Systems/Embedded", r"firmware|embedded|kernel|compiler|gpu|cuda|systems software|os\b|driver|silicon|performance|hpc|robotics|autonomy|flight software|graphics"),
    ("Mobile", r"\bios\b|android|mobile"),
    ("Frontend/Full-stack", r"front[- ]?end|full[- ]?stack|web|\bui\b"),
    ("SWE (General)", r".*"),
]
_TRACKS = [(n, re.compile(p, re.I)) for n, p in TRACKS]

# 팀/부서가 ML이면 "Member of Technical Staff" 같은 애매한 제목을 ML로 보정
_ML_TEAM = re.compile(r"research|machine learning|\bai\b|\bml\b|model|alignment|interpretability|training|inference", re.I)


_NOT_ENG = re.compile(r"^(senior |sr\.? |principal |lead )?(account|sales|recruit|marketing|technical program|program|product) ", re.I)


def is_target(title: str) -> bool:
    if _STRONG.search(title) and not _NOT_ENG.search(title):
        return True
    return bool(_INCLUDE.search(title)) and not _EXCLUDE.search(title)


def track_of(title: str, team: str = "") -> str:
    for name, rx in _TRACKS:
        if rx.search(title):
            if name == "SWE (General)" and team and _ML_TEAM.search(team):
                return "ML/AI Eng"
            return name
    return "SWE (General)"


_LEVELS = [
    ("Intern/New Grad", r"intern|new grad|university|graduate|early career|entry|apprentice|student|phd resident|\bresidency"),
    ("Principal+", r"principal|distinguished|fellow|\bl8\b|\bl9\b|partner\b|architect"),
    ("Staff", r"\bstaff\b|\bl7\b|\bic5\b|\bict5\b|\bt5\b|\bl67\b"),
    ("Senior", r"senior|\bsr\.?\b|\bl6\b|\bl5\b|\bsde ?iii\b|\biii\b|\bic4\b|\bict4\b|lead\b"),
    ("Mid", r"\bii\b|\bsde ?ii\b|\bl4\b|\bic3\b|\bict3\b"),
    ("Junior", r"junior|\bjr\.?\b|associate|\bi\b|\bl3\b|\bsde ?i\b"),
]
_LEVELS = [(n, re.compile(p, re.I)) for n, p in _LEVELS]


def level_of(title: str) -> str:
    for name, rx in _LEVELS:
        if rx.search(title):
            return name
    return "Unspecified"


_YOE = re.compile(
    r"(\d{1,2})\s*\+?\s*(?:-|–|to)?\s*(?:\d{1,2})?\s*\+?\s*years?(?:\s+of)?(?:\s+\w+){0,6}?\s+"
    r"(?:experience|industry|professional|software|engineering|work)",
    re.I,
)


def min_years(desc: str) -> int | None:
    """JD에 적힌 '최소 N년' 중 가장 작은 값 (학위 기간 등 오탐 방지 위해 0~20만)."""
    vals = [int(m.group(1)) for m in _YOE.finditer(desc or "")]
    vals = [v for v in vals if 0 < v <= 20]
    return min(vals) if vals else None
