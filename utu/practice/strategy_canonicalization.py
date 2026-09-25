"""Deterministic strategy representations for conservative L0 clustering."""

# ruff: noqa: E501

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from .experience_models import ExperienceRecord

CANONICAL_STRATEGY_VERSION = "l0_strategy_v1"

_UNKNOWN_VALUES = {"", "unknown", "null", "none"}
_CLAUSE_SPLIT = re.compile(r"(?<=[.!?\u3002\uff01\uff1f])\s*|[;\uff1b]\s*|\n+")
_SPACE = re.compile(r"\s+")
_LATIN_ANCHOR_TOKEN = re.compile(r"[a-z][a-z0-9_-]{2,}", re.I)
_CJK_RUN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]+")
_TRIGGER_PREFIX = re.compile(
    r"^(?:when|if|for|given|in problems?|\u5f53|\u82e5|\u5982\u679c|\u9047\u5230|\u5904\u7406|\u9898\u76ee)",
    re.I,
)
_BOUNDARY_MARKER = re.compile(
    r"\b(?:only applies?|not applicable|unless|except|fails? when|requires?|provided that|domain|boundary)\b|"
    r"\u5931\u6548\u8fb9\u754c|\u4ec5\u9002\u7528|\u4e0d\u9002\u7528|\u4e0d\u80fd|\u9664\u975e|\u5b9a\u4e49\u57df|\u9002\u7528\u8fb9\u754c",
    re.I,
)
_TOOL_NOISE = re.compile(
    r"\b(?:tool|python|code|environment|infrastructure|retry|interactive\s*shell)\b.*"
    r"\b(?:fail|error|unavailable|stop|retry)\b|"
    r"\u5de5\u5177.*(?:\u5931\u8d25|\u9519\u8bef|\u91cd\u8bd5|\u73af\u5883)|"
    r"(?:\u5931\u8d25|\u9519\u8bef).*\u5de5\u5177",
    re.I,
)
_GENERIC_VERIFICATION = re.compile(
    r"\b(?:verify|verification|check|cross-check|back-substitut|sanity check|final answer|lowest terms|"
    r"answer format|ground truth)\b|"
    r"\u56de\u4ee3|\u590d\u6838|\u81ea\u68c0|\u9a8c\u8bc1|\u6700\u7ec8\u7b54\u6848|"
    r"\u7b54\u6848\u683c\u5f0f|\u6700\u7b80",
    re.I,
)
_GENERIC_VERIFICATION_PREFIX = re.compile(
    r"^(?:(?:also|always|explicitly|finally|independently)\s+)*"
    r"(?:verify|verification|check|cross-check|back-substitut|sanity check|"
    r"\u56de\u4ee3|\u590d\u6838|\u81ea\u68c0|\u9a8c\u8bc1)",
    re.I,
)

_NON_STRATEGIC_SUBSTITUTION = re.compile(
    r"\b(?:back|direct)\s*[- ]?substitut\w*\b|\u56de\u4ee3|\u76f4\u63a5\u4ee3\u5165",
    re.I,
)
_GENERIC_ANCHOR_TOKENS = {
    "also",
    "and",
    "answer",
    "answers",
    "are",
    "as",
    "by",
    "calculate",
    "check",
    "compute",
    "condition",
    "conditions",
    "directly",
    "equation",
    "equations",
    "final",
    "first",
    "for",
    "formula",
    "frac",
    "from",
    "given",
    "into",
    "is",
    "math",
    "method",
    "of",
    "problem",
    "problems",
    "result",
    "results",
    "solve",
    "solving",
    "sqrt",
    "strategy",
    "that",
    "the",
    "then",
    "to",
    "use",
    "using",
    "value",
    "values",
    "verify",
    "when",
    "with",
    "使用",
    "先用",
    "检查",
    "求解",
    "方法",
    "最后",
    "条件",
    "结果",
    "题目",
    "问题",
    "验证",
}
_MIN_FALLBACK_ANCHOR_OVERLAP = 0.18


@dataclass(frozen=True)
class CanonicalStrategyRepresentation:
    """Runtime-only decomposition of an L0 into strategy-bearing fields."""

    task_family: str | None
    trigger: str
    strategy: str
    procedure: tuple[str, ...]
    boundary: tuple[str, ...]
    ignored_generic: tuple[str, ...]
    strategy_labels: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["distinctive_strategy_labels"] = list(self.distinctive_strategy_labels)
        payload["auxiliary_strategy_labels"] = list(self.auxiliary_strategy_labels)
        payload["strategy_anchor_tokens"] = list(self.strategy_anchor_tokens)
        return payload

    @property
    def distinctive_strategy_labels(self) -> tuple[str, ...]:
        return tuple(label for label in self.strategy_labels if label not in AUXILIARY_STRATEGY_LABELS)

    @property
    def auxiliary_strategy_labels(self) -> tuple[str, ...]:
        return tuple(label for label in self.strategy_labels if label in AUXILIARY_STRATEGY_LABELS)

    @property
    def has_strategy_evidence(self) -> bool:
        return bool(self.strategy.strip() or any(item.strip() for item in self.procedure))

    @property
    def strategy_anchor_tokens(self) -> tuple[str, ...]:
        return _strategy_anchor_tokens(" ".join((self.strategy, *self.procedure)))

    @property
    def embedding_text(self) -> str:
        fields = [
            ("task_family", self.task_family or "unknown"),
            (
                "distinctive_strategy_labels",
                ", ".join(self.distinctive_strategy_labels) or "unknown",
            ),
            (
                "auxiliary_strategy_labels",
                ", ".join(self.auxiliary_strategy_labels) or "unknown",
            ),
            ("trigger", self.trigger),
            ("strategy", self.strategy),
            ("procedure", " | ".join(self.procedure)),
            ("boundary", " | ".join(self.boundary)),
        ]
        return "\n".join(f"{name}: {value}" for name, value in fields if value)

    @property
    def compatibility_text(self) -> str:
        fields = [
            f"task_family: {self.task_family or 'unknown'}",
            (f"distinctive_strategy_labels: {', '.join(self.distinctive_strategy_labels) or 'unknown'}"),
            f"strategy: {self.strategy}",
            f"procedure: {' | '.join(self.procedure)}",
        ]
        return "\n".join(field for field in fields if not field.endswith(": "))


@dataclass(frozen=True)
class StrategyCompatibilityDecision:
    compatible: bool
    reason: str
    core_similarity: float
    required_similarity: float
    shared_strategy_labels: tuple[str, ...]
    shared_distinctive_strategy_labels: tuple[str, ...]
    shared_auxiliary_strategy_labels: tuple[str, ...]
    strategy_anchor_similarity: float
    minimum_anchor_similarity: float
    left_task_family: str | None
    right_task_family: str | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


_TASK_FAMILY_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "solid_geometry",
        re.compile(
            r"\b(?:tetrahedron|pyramid|prism|polyhedron|3d|sphere.*planes?)\b|"
            r"\u68f1\u9525|\u68f1\u67f1|\u56db\u9762\u4f53|\u7acb\u4f53\u51e0\u4f55|\u5f02\u9762\u76f4\u7ebf",
            re.I,
        ),
    ),
    (
        "complex_numbers",
        re.compile(r"\bcomplex(?:-number)?|roots? of unity\b|\|z[-+]|\u590d\u6570|\u5355\u4f4d\u6839", re.I),
    ),
    (
        "geometric_probability",
        re.compile(
            r"\bgeometric probability|uniform.*(?:polygon|region)|random (?:arc|cover)\b|\u51e0\u4f55\u6982\u7387", re.I
        ),
    ),
    (
        "circle_geometry",
        re.compile(
            r"\b(?:circle|circular|radius|diameter|chord|concyclic|tangent circles?)\b|"
            r"\u5706\u76d8|\u5706\u5468|\u5706\u5fc3|\u534a\u5f84|\u76f4\u5f84|\u5f26|\u5171\u5706",
            re.I,
        ),
    ),
    (
        "polygon_geometry",
        re.compile(
            r"\b(?:polygon|octagon|rectangle|trapezoid|shoelace|area ratio)\b|"
            r"\u591a\u8fb9\u5f62|\u77e9\u5f62|\u68af\u5f62|\u9762\u79ef",
            re.I,
        ),
    ),
    (
        "triangle_geometry",
        re.compile(r"\b(?:triangle|altitude|hypotenuse)\b|\u4e09\u89d2\u5f62|\u659c\u8fb9|\u9ad8\u7ebf", re.I),
    ),
    (
        "combinatorial_geometry",
        re.compile(
            r"\b(?:plane triangulation|triangulate|lattice points?|colored points?|separat.*points?)\b|"
            r"\u5256\u5206\u4e3a\u4e09\u89d2\u5f62|\u6574\u70b9\u8ba1\u6570|\u7ea2\u84dd\u70b9|\u5206\u79bb.*\u70b9",
            re.I,
        ),
    ),
    (
        "trigonometry",
        re.compile(
            r"\b(?:trigonometric|sine|cosine|sin\b|cos\b|tan\b)\b|\u4e09\u89d2\u5f0f|\u6b63\u5f26|\u4f59\u5f26|\u6b63\u5207",
            re.I,
        ),
    ),
    (
        "number_theory_digits",
        re.compile(
            r"\b(?:digit(?:s| sum| replacement)?|base-?\w+ digits?|substring.*(?:number|digit))\b|"
            r"\u6570\u4f4d|\u5404\u4f4d\u6570\u5b57|\u6570\u5b57\u9636\u4e58|\u8fdb\u5236",
            re.I,
        ),
    ),
    (
        "number_theory_divisors",
        re.compile(
            r"\b(?:divisors?|prime factorization|divisor sum)\b|\u56e0\u6570|\u7ea6\u6570|\u7d20\u56e0\u6570", re.I
        ),
    ),
    (
        "diophantine_equations",
        re.compile(
            r"\b(?:diophantine|integer solutions?|integer quadratic)\b|\u4e0d\u5b9a\u65b9\u7a0b|\u6574\u6570\u89e3",
            re.I,
        ),
    ),
    (
        "number_theory_modular",
        re.compile(
            r"\b(?:modular|congruence|modulo|crt|last \w+ digits?)\b|\u540c\u4f59|\u6a21\s*\d|\u672b\u4f4d", re.I
        ),
    ),
    (
        "polynomials",
        re.compile(
            r"\b(?:polynomial|roots?|remainder theorem|coefficient of)\b|\u591a\u9879\u5f0f|\u65b9\u7a0b\u6839|\u4f59\u5f0f",
            re.I,
        ),
    ),
    (
        "inequalities",
        re.compile(
            r"\b(?:inequalit|greatest constant|cauchy|jensen|am-gm|minimum|maximum)\b|\u4e0d\u7b49\u5f0f|\u6700\u503c|\u6700\u5927\u503c|\u6700\u5c0f\u503c",
            re.I,
        ),
    ),
    (
        "sequences_and_series",
        re.compile(
            r"\b(?:sequence|recurrence|series|arithmetic progression|prefix sum)\b|\u6570\u5217|\u9012\u63a8|\u7ea7\u6570|\u7b49\u5dee\u6570\u5217",
            re.I,
        ),
    ),
    (
        "probability",
        re.compile(r"\b(?:probability|random|expected time|independent trials?)\b|\u6982\u7387|\u671f\u671b", re.I),
    ),
    (
        "combinatorics",
        re.compile(
            r"\b(?:counting|arrangements?|configurations?|matching|pigeonhole|involution)\b|\u8ba1\u6570|\u6392\u5217|\u7ec4\u5408|\u67d3\u8272",
            re.I,
        ),
    ),
    (
        "functional_equations",
        re.compile(r"\bfunctional equation|inverse function\b|\u51fd\u6570\u65b9\u7a0b|\u53cd\u51fd\u6570", re.I),
    ),
    (
        "rates_and_resources",
        re.compile(
            r"\b(?:work-rate|drain rate|resource-depletion|person-minutes)\b|\u5de5\u7a0b\u95ee\u9898|\u5de5\u4f5c\u7387",
            re.I,
        ),
    ),
    (
        "general_algebra",
        re.compile(
            r"\b(?:equation|algebra|expression|absolute value|logarithm)\b|\u65b9\u7a0b|\u4ee3\u6570|\u7edd\u5bf9\u503c|\u5bf9\u6570",
            re.I,
        ),
    ),
)


_STRATEGY_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "coordinate_vector_geometry",
        re.compile(
            r"\bcoordinate|vector method|dot product\b|\u5750\u6807\u6cd5|\u5411\u91cf\u6cd5|\u70b9\u79ef", re.I
        ),
    ),
    (
        "section_formula",
        re.compile(r"\bsection formula|directed ratio\b|\u5b9a\u6bd4\u5206\u70b9|\u6bd4\u4f8b\u70b9", re.I),
    ),
    (
        "euler_planar_double_count",
        re.compile(
            r"\bEuler(?:'s)? formula|plane triangulation|double count.*(?:edge|face)\b|\u6b27\u62c9\u516c\u5f0f|\u4e09\u89d2\u9762\u8fb9\u53cc\u91cd\u8ba1\u6570",
            re.I,
        ),
    ),
    (
        "vieta_newton_symmetric_sums",
        re.compile(
            r"\bVieta|Newton (?:sum|identit)|power sums?|symmetric products?\b|\u97e6\u8fbe|\u725b\u987f\u548c|\u5bf9\u79f0\u5f0f",
            re.I,
        ),
    ),
    (
        "complete_square_difference_squares",
        re.compile(
            r"\bcomplet(?:e|ing) the square|difference of squares\b|\u914d\u65b9|\u5e73\u65b9\u5dee",
            re.I,
        ),
    ),
    (
        "balanced_factor_pair_optimization",
        re.compile(
            r"\b(?:closest|balanced|near(?:est)?) factor pairs?\b|"
            r"\b(?:minimiz\w*|optim\w*).{0,80}factor pairs?\b|"
            r"\u6700\u63a5\u8fd1.*\u5e73\u65b9\u6839|\u56e0\u5b50\u5bf9.*\u6700\u5c0f",
            re.I,
        ),
    ),
    (
        "discriminant_boundary",
        re.compile(
            r"\bdiscriminant|vertex minimum|quadratic inequality\b|\u5224\u522b\u5f0f|\u9876\u70b9\u6700\u5c0f\u503c|\u4e8c\u6b21\u4e0d\u7b49\u5f0f",
            re.I,
        ),
    ),
    (
        "modular_exponent_cycle",
        re.compile(
            r"\bCarmichael|multiplicative order|Euler.*totient|exponent.*modulo|CRT\b|\u5361\u8fc8\u514b|\u6b27\u62c9\u51fd\u6570|\u4e58\u6cd5\u9636|\u4e2d\u56fd\u5269\u4f59",
            re.I,
        ),
    ),
    (
        "congruence_propagation",
        re.compile(
            r"\bcongruences?|sliding-window sums?|2-adic|infinite descent\b|\u540c\u4f59|\u6ed1\u52a8\u7a97\u53e3|2-adic|\u65e0\u7a77\u9012\u964d",
            re.I,
        ),
    ),
    (
        "factorial_digit_bounding",
        re.compile(
            r"\bdigit factorial|factorial bound|factorial growth\b|\u6570\u5b57\u9636\u4e58|\u9636\u4e58\u754c|\u9636\u4e58\u589e\u957f",
            re.I,
        ),
    ),
    (
        "inclusion_exclusion_complement",
        re.compile(
            r"\binclusion.?exclusion|complement count|subtract.*collinear\b|\u5bb9\u65a5|\u8865\u96c6\u8ba1\u6570", re.I
        ),
    ),
    (
        "generating_blocks_convolution",
        re.compile(
            r"\bcoefficient convolution|common sum.*count|ordered digit assignments\b|\u7cfb\u6570\u5377\u79ef|\u6309\u516c\u5171\u548c",
            re.I,
        ),
    ),
    (
        "normalize_and_reduce_dimension",
        re.compile(
            r"\bnormalize by|homogeneous|set .*ratio|reduce to one variable\b|\u9f50\u6b21|\u5f52\u4e00\u5316|\u6362\u5143.*\u4e00\u7ef4",
            re.I,
        ),
    ),
    (
        "substitution_linearization",
        re.compile(
            r"\bsubstitut|linearize|introduce .*variable|set .*=" r"\b|\u6362\u5143|\u7ebf\u6027\u5316|\u8bbe.*=", re.I
        ),
    ),
    (
        "interval_containment_extrema",
        re.compile(
            r"\bsubset|containment|projection.*minimum|check.*endpoints?\b|\u5b50\u96c6|\u5305\u542b|\u6295\u5f71.*\u6700\u4f4e\u70b9|\u7aef\u70b9",
            re.I,
        ),
    ),
    (
        "prime_exponent_divisor_count",
        re.compile(
            r"\bprime exponent|random divisor|divisors?.*divisible|\(e_i-f_i\+1\)\b|\u8d28\u56e0\u6570\u6307\u6570|\u7ea6\u6570\u4e2a\u6570",
            re.I,
        ),
    ),
    (
        "area_coordinates_determinant",
        re.compile(
            r"\bshoelace|determinant.*area|area ratio|coordinate.*area\b|\u978b\u5e26\u516c\u5f0f|\u884c\u5217\u5f0f.*\u9762\u79ef|\u9762\u79ef\u6bd4",
            re.I,
        ),
    ),
    (
        "circle_distance_extrema",
        re.compile(
            r"\bcircle.*distance|farthest point|nearest point|\|C-A\|\+r\b|\u5706\u4e0a\u70b9.*\u8ddd\u79bb|\u6700\u8fdc\u70b9|\u6700\u8fd1\u70b9",
            re.I,
        ),
    ),
    (
        "piecewise_absolute_value",
        re.compile(
            r"\bpiecewise|nested absolute|breakpoints?|L_1.*balls?\b|\u5206\u6bb5|\u5d4c\u5957\u7edd\u5bf9\u503c|\u65ad\u70b9",
            re.I,
        ),
    ),
    (
        "cauchy_equality_conditions",
        re.compile(
            r"\bCauchy|equality conditions?|maximum possible value\b|\u67ef\u897f|\u53d6\u7b49\u6761\u4ef6", re.I
        ),
    ),
    (
        "recurrence_trigonometric_substitution",
        re.compile(
            r"\brecurrence.*(?:sin|cos)|set .*sin.*theta|trigonometric substitution\b|\u9012\u63a8.*\u6b63\u5f26|\u4e09\u89d2\u6362\u5143",
            re.I,
        ),
    ),
    (
        "logarithmic_derivative_roots",
        re.compile(
            r"\blogarithmic derivative|roots of unity.*sum|P'\(.*\)/P\b|\u5bf9\u6570\u5bfc\u6570|\u5355\u4f4d\u6839.*\u6c42\u548c",
            re.I,
        ),
    ),
    (
        "change_of_base_logarithms",
        re.compile(
            r"\bchange[- ]of[- ]base|logarithm.*product\b|\u6362\u5e95\u516c\u5f0f|\u5bf9\u6570\u6c42\u548c", re.I
        ),
    ),
    (
        "tangency_common_point_derivative",
        re.compile(
            r"\btangency.*common point|equal derivatives?|implicit(?:ly)? differentiat\b|\u76f8\u5207.*\u516c\u5171\u70b9|\u5bfc\u6570\u76f8\u7b49|\u9690\u51fd\u6570\u6c42\u5bfc",
            re.I,
        ),
    ),
    (
        "symmetry_involution",
        re.compile(
            r"\bsign-reversing involution|symmetry.*half|pair.*opposite sign\b|\u5bf9\u5408|\u7b26\u53f7\u53cd\u8f6c|\u5bf9\u79f0.*\u4e00\u534a",
            re.I,
        ),
    ),
    (
        "pigeonhole_runs",
        re.compile(r"\bpigeonhole|binary string|runs?.*at most\b|\u62bd\u5c49|\u8fde\u7eed\u6bb5", re.I),
    ),
    (
        "conservation_accounting",
        re.compile(
            r"\bconservation|person-minutes|total resource|balance equation\b|\u5b88\u6052|\u603b\u91cf\u5e73\u8861",
            re.I,
        ),
    ),
    (
        "remainder_theorem_base_digits",
        re.compile(
            r"\bremainder theorem|base-.*digits|P\(b\)=N\b|\u4f59\u6570\u5b9a\u7406|\u8fdb\u5236\u6570\u5b57", re.I
        ),
    ),
    (
        "finite_factor_enumeration",
        re.compile(
            r"\benumerat.*(?:divisor|factor)|finite factor|closest factor pairs?\b|\u679a\u4e3e\u56e0\u5b50|\u6709\u9650\u56e0\u5b50",
            re.I,
        ),
    ),
)


# These describe broadly useful operations, but do not by themselves identify
# one reusable strategy. They can refine a distinctive label or participate in
# a high-confidence semantic fallback; they never lower the compatibility bar.
AUXILIARY_STRATEGY_LABELS = frozenset(
    {
        "area_coordinates_determinant",
        "congruence_propagation",
        "coordinate_vector_geometry",
        "discriminant_boundary",
        "finite_factor_enumeration",
        "inclusion_exclusion_complement",
        "interval_containment_extrema",
        "normalize_and_reduce_dimension",
        "section_formula",
        "substitution_linearization",
        "vieta_newton_symmetric_sums",
    }
)


def _normalise_text(text: str) -> str:
    return _SPACE.sub(" ", (text or "").replace("\\n", "\n")).strip()


def _known_metadata(value: object) -> str | None:
    raw = str(getattr(value, "value", value) or "").strip().lower()
    if raw in _UNKNOWN_VALUES:
        return None
    return re.sub(r"[^a-z0-9]+", "_", raw).strip("_") or None


def _first_label(text: str, rules: tuple[tuple[str, re.Pattern[str]], ...]) -> str | None:
    return next((label for label, pattern in rules if pattern.search(text)), None)


def _strategy_labels(text: str) -> tuple[str, ...]:
    strategy_text = _NON_STRATEGIC_SUBSTITUTION.sub(" ", text)
    return tuple(sorted(label for label, pattern in _STRATEGY_RULES if pattern.search(strategy_text)))


def _strategy_anchor_tokens(text: str) -> tuple[str, ...]:
    normalized = _NON_STRATEGIC_SUBSTITUTION.sub(" ", text.lower())
    tokens = {token for token in _LATIN_ANCHOR_TOKEN.findall(normalized) if token not in _GENERIC_ANCHOR_TOKENS}
    for run in _CJK_RUN.findall(normalized):
        if len(run) == 1:
            tokens.add(run)
            continue
        tokens.update(
            token
            for token in (run[index : index + 2] for index in range(len(run) - 1))
            if token not in _GENERIC_ANCHOR_TOKENS
        )
    return tuple(sorted(tokens))


def _jaccard_similarity(left: tuple[str, ...], right: tuple[str, ...]) -> float:
    left_tokens = set(left)
    right_tokens = set(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _trim(value: str, limit: int = 520) -> str:
    value = value.strip(" ,-:")
    return value if len(value) <= limit else value[: limit - 3].rstrip() + "..."


def canonicalize_l0_strategy(record: ExperienceRecord) -> CanonicalStrategyRepresentation:
    """Extract strategy-bearing text while excluding generic operational advice."""

    text = _normalise_text(record.content)
    clauses = [_trim(clause) for clause in _CLAUSE_SPLIT.split(text) if clause.strip()]
    retained: list[str] = []
    ignored: list[str] = []
    boundaries: list[str] = []
    strategy_clauses: list[str] = []
    procedure: list[str] = []

    for clause in clauses:
        labels = _strategy_labels(clause)
        if _TOOL_NOISE.search(clause) or (
            _GENERIC_VERIFICATION.search(clause) and (not labels or _GENERIC_VERIFICATION_PREFIX.search(clause))
        ):
            ignored.append(clause)
            continue
        retained.append(clause)
        if _BOUNDARY_MARKER.search(clause):
            boundaries.append(clause)
        elif labels:
            strategy_clauses.append(clause)
        else:
            procedure.append(clause)

    trigger = next(
        (clause for clause in retained if _TRIGGER_PREFIX.search(clause)),
        retained[0] if retained else "",
    )
    if not strategy_clauses and trigger:
        strategy_clauses = [trigger]
    core_text = " ".join([*strategy_clauses, *procedure[:3]])
    labels = _strategy_labels(core_text)
    metadata_family = _known_metadata(record.task_family)
    task_family = metadata_family or _first_label(text, _TASK_FAMILY_RULES)
    return CanonicalStrategyRepresentation(
        task_family=task_family,
        trigger=_trim(trigger),
        strategy=_trim(" ".join(strategy_clauses[:2]), 900),
        procedure=tuple(_trim(clause) for clause in procedure[:4]),
        boundary=tuple(_trim(clause) for clause in boundaries[:3]),
        ignored_generic=tuple(_trim(clause) for clause in ignored[:6]),
        strategy_labels=labels,
    )


def assess_strategy_compatibility(
    left: CanonicalStrategyRepresentation,
    right: CanonicalStrategyRepresentation,
    *,
    core_similarity: float,
    compatibility_threshold: float,
    fallback_threshold: float,
) -> StrategyCompatibilityDecision:
    """Decide whether two recalled L0s support the same reusable strategy."""

    left_labels = set(left.strategy_labels)
    right_labels = set(right.strategy_labels)
    shared_labels = tuple(sorted(left_labels & right_labels))
    shared_distinctive = tuple(label for label in shared_labels if label not in AUXILIARY_STRATEGY_LABELS)
    shared_auxiliary = tuple(label for label in shared_labels if label in AUXILIARY_STRATEGY_LABELS)
    anchor_similarity = _jaccard_similarity(
        left.strategy_anchor_tokens,
        right.strategy_anchor_tokens,
    )

    def decision(*, compatible: bool, reason: str, required_similarity: float):
        return StrategyCompatibilityDecision(
            compatible=compatible,
            reason=reason,
            core_similarity=core_similarity,
            required_similarity=required_similarity,
            shared_strategy_labels=shared_labels,
            shared_distinctive_strategy_labels=shared_distinctive,
            shared_auxiliary_strategy_labels=shared_auxiliary,
            strategy_anchor_similarity=anchor_similarity,
            minimum_anchor_similarity=(0.0 if shared_distinctive else _MIN_FALLBACK_ANCHOR_OVERLAP),
            left_task_family=left.task_family,
            right_task_family=right.task_family,
        )

    if not left.has_strategy_evidence or not right.has_strategy_evidence:
        return decision(
            compatible=False,
            reason="insufficient_strategy_evidence",
            required_similarity=fallback_threshold,
        )
    if left.task_family and right.task_family and left.task_family != right.task_family:
        return decision(
            compatible=False,
            reason="task_family_mismatch",
            required_similarity=compatibility_threshold,
        )
    if left_labels and right_labels and not shared_labels:
        return decision(
            compatible=False,
            reason="strategy_label_mismatch",
            required_similarity=compatibility_threshold,
        )
    if not shared_distinctive and anchor_similarity < _MIN_FALLBACK_ANCHOR_OVERLAP:
        return decision(
            compatible=False,
            reason="low_strategy_anchor_overlap",
            required_similarity=fallback_threshold,
        )
    required_similarity = compatibility_threshold if shared_distinctive else fallback_threshold
    compatible = core_similarity >= required_similarity
    if compatible:
        reason = "compatible_distinctive_strategy" if shared_distinctive else "compatible_high_confidence_fallback"
    elif shared_auxiliary:
        reason = "auxiliary_only_strategy_overlap"
    elif shared_labels:
        reason = "low_strategy_core_similarity"
    else:
        reason = "insufficient_strategy_evidence"
    return decision(
        compatible=compatible,
        reason=reason,
        required_similarity=required_similarity,
    )


__all__ = [
    "AUXILIARY_STRATEGY_LABELS",
    "CANONICAL_STRATEGY_VERSION",
    "CanonicalStrategyRepresentation",
    "StrategyCompatibilityDecision",
    "assess_strategy_compatibility",
    "canonicalize_l0_strategy",
]
