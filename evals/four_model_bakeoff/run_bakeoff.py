#!/usr/bin/env python3
"""Run the frozen four-model Bazi foundation benchmark.

The administration prompt and model/config choices live in the preceding protocol
PR. This file only materializes the frozen question recipe, calls providers, and
computes deterministic metrics. Reports are gitignored and contain synthetic data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from itertools import combinations_with_replacement
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "consult-engine"))

import gateway  # noqa: E402
import luck  # noqa: E402

LETTERS = "ABCD"
TEN_GODS = ("比肩", "劫财", "食神", "伤官", "偏印", "正印", "偏财", "正财", "七杀", "正官")
ELEMENTS = ("木", "火", "土", "金", "水")


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _seed(*parts: Any) -> int:
    raw = "|".join(str(part) for part in parts)
    return int(hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16], 16)


def load_config() -> dict:
    return json.loads((HERE / "config.json").read_text(encoding="utf-8"))


def _question(qid: str, category: str, text: str, correct: str,
              distractors: list[str]) -> dict:
    options = [correct]
    for candidate in distractors:
        if candidate != correct and candidate not in options:
            options.append(candidate)
        if len(options) == 4:
            break
    if len(options) != 4:
        raise ValueError(f"{qid} 无法构造四个唯一选项")
    return {
        "id": qid,
        "category": category,
        "question": text,
        "correct": correct,
        "semantic_options": options,
    }


def _pick_distractors(values: list[str] | tuple[str, ...], correct: str,
                      rng: random.Random) -> list[str]:
    candidates = [value for value in values if value != correct]
    rng.shuffle(candidates)
    return candidates[:3]


def _build_shishen(seed: int) -> list[dict]:
    grouped: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for day_stem in luck.STEMS:
        for other_stem in luck.STEMS:
            grouped[luck.shishen(day_stem, other_stem)].append((day_stem, other_stem))

    out = []
    for god_index, god in enumerate(TEN_GODS):
        pairs = list(grouped[god])
        random.Random(_seed(seed, "shishen-pairs", god)).shuffle(pairs)
        for pair_index, (day_stem, other_stem) in enumerate(pairs[:2]):
            rng = random.Random(_seed(seed, "shishen-options", god, pair_index))
            out.append(_question(
                f"SS{god_index * 2 + pair_index + 1:02d}",
                "shishen",
                f"以{day_stem}为日主，{other_stem}相对日主的十神是什么？",
                god,
                _pick_distractors(TEN_GODS, god, rng),
            ))
    return out


def _relation_text(rels: tuple[str, ...] | list[str]) -> str:
    return "、".join(rels)


def _build_branch_rel(seed: int) -> list[dict]:
    grouped: dict[tuple[str, ...], list[tuple[str, str]]] = defaultdict(list)
    for first, second in combinations_with_replacement(luck.BRANCHES, 2):
        grouped[tuple(luck.branch_rel(first, second))].append((first, second))

    signatures = sorted(grouped)
    queues: dict[tuple[str, ...], list[tuple[str, str]]] = {}
    for signature in signatures:
        queues[signature] = list(grouped[signature])
        random.Random(_seed(seed, "branch-pairs", signature)).shuffle(queues[signature])

    selected: list[tuple[tuple[str, ...], tuple[str, str]]] = []
    while len(selected) < 16:
        progressed = False
        for signature in signatures:
            if queues[signature] and len(selected) < 16:
                selected.append((signature, queues[signature].pop()))
                progressed = True
        if not progressed:
            raise ValueError("地支关系题库不足 16 题")

    all_answers = [_relation_text(signature) for signature in signatures]
    out = []
    for index, (signature, (first, second)) in enumerate(selected, 1):
        correct = _relation_text(signature)
        rng = random.Random(_seed(seed, "branch-options", index))
        out.append(_question(
            f"BR{index:02d}",
            "branch_rel",
            f"按六合、六冲、六害、刑、三合半合、同气规则，地支{first}与{second}有哪些关系？多项并存时选择完整组合。",
            correct,
            _pick_distractors(all_answers, correct, rng),
        ))
    return out


def _element_text(tally: dict[str, int]) -> str:
    return "、".join(f"{element}{tally[element]}" for element in ELEMENTS)


def _element_distractors(tally: dict[str, int]) -> list[str]:
    candidates = []
    counts = [tally[element] for element in ELEMENTS]
    for source in range(len(ELEMENTS)):
        if counts[source] == 0:
            continue
        for offset in range(1, len(ELEMENTS)):
            target = (source + offset) % len(ELEMENTS)
            altered = counts.copy()
            altered[source] -= 1
            altered[target] += 1
            text = "、".join(f"{element}{altered[i]}" for i, element in enumerate(ELEMENTS))
            if text not in candidates:
                candidates.append(text)
    return candidates[:3]


def _build_elements() -> list[dict]:
    cases = [
        ("甲乙丙丁", "子丑寅卯"),
        ("戊己庚辛", "辰巳午未"),
        ("壬癸甲丙", "申酉戌亥"),
        ("乙丁己辛", "子寅午酉"),
        ("甲甲庚庚", "卯卯申申"),
        ("丙丁戊己", "巳午辰戌"),
        ("壬癸壬癸", "子亥丑辰"),
        ("乙丙辛壬", "寅巳酉亥"),
    ]
    out = []
    for index, (stems, branches) in enumerate(cases, 1):
        tally = luck.chart_elements(list(stems), list(branches))
        correct = _element_text(tally)
        out.append(_question(
            f"EL{index:02d}",
            "chart_elements",
            f"只按天干与地支本气计数，不计藏干。天干为{'、'.join(stems)}，地支为{'、'.join(branches)}，五行数量是哪一项？",
            correct,
            _element_distractors(tally),
        ))
    return out


def _dayun_text(result: dict) -> str:
    return f"{result['direction']}；{result['start_detail']}；首运{result['periods'][0]['ganzhi']}"


def _build_dayun() -> list[dict]:
    cases = [
        ("丙寅", "甲", "male", 6.0, 9.0, 1990),
        ("丁卯", "甲", "female", 6.0, 9.0, 1991),
        ("戊辰", "乙", "female", 8.0, 4.5, 1992),
        ("己巳", "乙", "male", 8.0, 4.5, 1993),
        ("庚午", "丙", "male", 3.25, 7.0, 1994),
        ("辛未", "丁", "female", 11.0, 2.25, 1995),
        ("壬申", "庚", "female", 5.0, 6.75, 1996),
        ("癸酉", "癸", "male", 9.0, 1.5, 1997),
    ]
    out = []
    for index, (month_gz, year_stem, gender, days_next, days_prev, birth_year) in enumerate(cases, 1):
        result = luck.dayun(month_gz, year_stem, gender, days_next, days_prev, birth_year, count=2)
        opposite_gender = "female" if gender == "male" else "male"
        opposite = luck.dayun(month_gz, year_stem, opposite_gender, days_next, days_prev, birth_year, count=2)
        correct = _dayun_text(result)
        age_plus_one = dict(result)
        age_plus_one["start_detail"] = (
            f"{result['start_age'] + 1}岁{result['start_months']}个月"
            if result["start_months"] else f"{result['start_age'] + 1}岁整"
        )
        second_luck = dict(result)
        second_luck["periods"] = [result["periods"][1]]
        gender_text = "男" if gender == "male" else "女"
        out.append(_question(
            f"DY{index:02d}",
            "dayun",
            (
                f"月柱{month_gz}、年干{year_stem}、{gender_text}命；出生到下一节{days_next:g}天、"
                f"距上一节{days_prev:g}天。按阳年男阴年女顺排、其余逆排，三天折一年并四舍五入到月，"
                "起运方向、起运岁月和首步大运是哪一项？"
            ),
            correct,
            [_dayun_text(opposite), _dayun_text(age_plus_one), _dayun_text(second_luck)],
        ))
    return out


def _build_calendar() -> list[dict]:
    out = []
    for index, year in enumerate((1984, 1990, 2000, 2024), 1):
        correct = luck.year_ganzhi(year)
        distractors = [luck.year_ganzhi(year - 1), luck.year_ganzhi(year + 1), luck.year_ganzhi(year + 10)]
        out.append(_question(
            f"GZ{index:02d}",
            "ganzhi_calendar",
            f"以 1984 年为甲子年锚点，{year} 年的干支是哪一项？",
            correct,
            distractors,
        ))

    month_cases = (("甲", 1), ("乙", 4), ("丙", 7), ("丁", 10))
    for offset, (year_stem, month_number) in enumerate(month_cases, 5):
        months = luck.liuyue_ganzhi(year_stem)
        correct = months[month_number - 1]
        distractors = [
            months[(month_number - 2) % 12],
            months[month_number % 12],
            luck.liuyue_ganzhi(luck.STEMS[(luck.STEMS.index(year_stem) + 1) % 10])[month_number - 1],
        ]
        out.append(_question(
            f"GZ{offset:02d}",
            "ganzhi_calendar",
            f"按五虎遁排流月，流年年干为{year_stem}，以寅月为第 1 月，第 {month_number} 个流月干支是哪一项？",
            correct,
            distractors,
        ))
    return out


def build_question_bank(config: dict) -> list[dict]:
    seed = int(config["seed"])
    questions = (
        _build_shishen(seed)
        + _build_branch_rel(seed)
        + _build_elements()
        + _build_dayun()
        + _build_calendar()
    )
    counts: dict[str, int] = defaultdict(int)
    ids = set()
    for item in questions:
        counts[item["category"]] += 1
        if item["id"] in ids:
            raise ValueError(f"重复题号:{item['id']}")
        ids.add(item["id"])
        if item["correct"] not in item["semantic_options"] or len(set(item["semantic_options"])) != 4:
            raise ValueError(f"{item['id']} 选项不合法")
    if len(questions) != int(config["questions_per_repeat"]):
        raise ValueError("题量与冻结配置不一致")
    if dict(counts) != config["categories"]:
        raise ValueError(f"分类配额与冻结配置不一致:{dict(counts)}")
    return questions


def blind_model_map(config: dict) -> dict[str, dict]:
    models = [dict(model) for model in config["models"]]
    random.Random(_seed(config["seed"], "blind-model-map")).shuffle(models)
    return {f"模型{LETTERS[index]}": model for index, model in enumerate(models)}


def materialize_questions(questions: list[dict], config: dict, blind_id: str,
                          repetition: int) -> list[dict]:
    materialized = []
    for item in questions:
        options = list(item["semantic_options"])
        random.Random(_seed(config["seed"], "options", blind_id, repetition, item["id"])).shuffle(options)
        option_map = {letter: value for letter, value in zip(LETTERS, options)}
        materialized.append({
            "id": item["id"],
            "category": item["category"],
            "question": item["question"],
            "options": option_map,
            "expected_choice": next(letter for letter, value in option_map.items() if value == item["correct"]),
            "expected_value": item["correct"],
        })
    random.Random(_seed(config["seed"], "question-order", blind_id, repetition)).shuffle(materialized)
    return materialized


def public_batch(items: list[dict]) -> list[dict]:
    return [{key: item[key] for key in ("id", "category", "question", "options")} for item in items]


def parse_answers(text: str, expected_ids: list[str]) -> tuple[dict[str, str], bool, list[str]]:
    errors = []
    try:
        payload = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        errors.append("response_not_strict_json")
        # Knowledge accuracy and protocol compliance are separate metrics. Recover a
        # single embedded JSON object for answer scoring, while keeping schema_valid
        # false so fences/explanations still count as a formatting failure.
        if not isinstance(text, str) or "{" not in text or "}" not in text:
            return {}, False, errors
        try:
            payload = json.loads(text[text.find("{"):text.rfind("}") + 1])
        except json.JSONDecodeError:
            return {}, False, errors
    if not isinstance(payload, dict) or set(payload) != {"answers"}:
        return {}, False, ["root_schema_invalid"]
    rows = payload.get("answers")
    if not isinstance(rows, list):
        return {}, False, ["answers_not_list"]

    answers: dict[str, str] = {}
    received_order = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"id", "answer"}:
            errors.append("answer_row_schema_invalid")
            continue
        qid, answer = row.get("id"), row.get("answer")
        if not isinstance(qid, str) or answer not in LETTERS:
            errors.append("answer_value_invalid")
            continue
        if qid in answers:
            errors.append(f"duplicate_id:{qid}")
            continue
        answers[qid] = answer
        received_order.append(qid)

    expected_set = set(expected_ids)
    if set(answers) - expected_set:
        errors.append("unexpected_ids")
    if expected_set - set(answers):
        errors.append("missing_ids")
    if received_order != expected_ids:
        errors.append("order_mismatch")
    answers = {qid: answer for qid, answer in answers.items() if qid in expected_set}
    return answers, not errors, sorted(set(errors))


def _new_checkpoint(config: dict, questions: list[dict]) -> dict:
    return {
        "schema_version": "four-model-bakeoff-result-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": None,
        "config_hash": _digest(config),
        "question_bank_hash": _digest(questions),
        "model_blind_map": blind_model_map(config),
        "runs": {},
        "summary": None,
    }


def _load_checkpoint(path: Path, config: dict, questions: list[dict]) -> dict:
    if not path.exists():
        return _new_checkpoint(config, questions)
    state = json.loads(path.read_text(encoding="utf-8"))
    if state.get("config_hash") != _digest(config):
        raise ValueError("已有结果的 config_hash 与冻结配置不一致，请换一个输出文件")
    if state.get("question_bank_hash") != _digest(questions):
        raise ValueError("已有结果的题库哈希不一致，请换一个输出文件")
    return state


def _save_checkpoint(path: Path, state: dict) -> None:
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def _batch_key(repetition: int, batch_index: int) -> str:
    return f"r{repetition + 1}-b{batch_index + 1}"


def _token_totals(usage: dict) -> tuple[int, int, int]:
    input_tokens = usage.get("input_tokens", usage.get("prompt_tokens", usage.get("promptTokenCount", 0))) or 0
    output_tokens = usage.get("output_tokens", usage.get("completion_tokens", usage.get("candidatesTokenCount", 0))) or 0
    total_tokens = usage.get("total_tokens", usage.get("totalTokenCount", input_tokens + output_tokens)) or 0
    return int(input_tokens), int(output_tokens), int(total_tokens)


def summarize(state: dict, config: dict, questions: list[dict]) -> dict:
    question_by_id = {item["id"]: item for item in questions}
    total_expected = int(config["questions_per_repeat"]) * int(config["repetitions"])
    batch_total = (int(config["questions_per_repeat"]) // int(config["batch_size"])) * int(config["repetitions"])
    models_summary = {}

    for blind_id, model in state["model_blind_map"].items():
        records = state.get("runs", {}).get(blind_id, {})
        correct = answered = schema_valid_batches = completed_batches = 0
        latency = 0.0
        input_tokens = output_tokens = total_tokens = 0
        category_total: dict[str, int] = defaultdict(int)
        category_correct: dict[str, int] = defaultdict(int)
        repeat_values: dict[str, dict[int, str]] = defaultdict(dict)

        for repetition in range(int(config["repetitions"])):
            materialized = materialize_questions(questions, config, blind_id, repetition)
            for batch_index in range(0, len(materialized), int(config["batch_size"])):
                batch_number = batch_index // int(config["batch_size"])
                record = records.get(_batch_key(repetition, batch_number))
                if not record or record.get("status") != "success":
                    continue
                completed_batches += 1
                schema_valid_batches += int(bool(record.get("schema_valid")))
                latency += float(record.get("latency_seconds", 0))
                ti, to, tt = _token_totals(record.get("token_usage", {}))
                input_tokens += ti
                output_tokens += to
                total_tokens += tt
                decoded = record.get("decoded_answers", {})
                for item in materialized[batch_index:batch_index + int(config["batch_size"])]:
                    category_total[item["category"]] += 1
                    value = decoded.get(item["id"])
                    if value is None:
                        continue
                    answered += 1
                    repeat_values[item["id"]][repetition] = value
                    if value == question_by_id[item["id"]]["correct"]:
                        correct += 1
                        category_correct[item["category"]] += 1

        stable = 0
        for qid in question_by_id:
            values = repeat_values.get(qid, {})
            if len(values) == int(config["repetitions"]) and len(set(values.values())) == 1:
                stable += 1
        eligible = completed_batches == batch_total and answered == total_expected
        models_summary[blind_id] = {
            "family": model["family"],
            "provider": model["provider"],
            "model_id": model["model_id"],
            "ranking_eligible": eligible,
            "completed_batches": completed_batches,
            "expected_batches": batch_total,
            "coverage": answered / total_expected,
            "correct": correct,
            "expected_answers": total_expected,
            "exact_choice_accuracy": correct / total_expected,
            "missing_answer_rate": (total_expected - answered) / total_expected,
            "schema_valid_rate": schema_valid_batches / batch_total,
            "cross_repeat_stability": stable / len(question_by_id),
            "category_accuracy": {
                category: (category_correct[category] / total if total else 0.0)
                for category, total in sorted(category_total.items())
            },
            "latency_seconds": round(latency, 3),
            "token_usage": {
                "input": input_tokens,
                "output": output_tokens,
                "total": total_tokens,
            },
        }

    eligible_rows = [
        (blind_id, row) for blind_id, row in models_summary.items() if row["ranking_eligible"]
    ]
    eligible_rows.sort(key=lambda pair: (-pair[1]["exact_choice_accuracy"], pair[0]))
    leader_ids = []
    if eligible_rows:
        top_score = eligible_rows[0][1]["exact_choice_accuracy"]
        leader_ids = [blind_id for blind_id, row in eligible_rows if row["exact_choice_accuracy"] == top_score]
    return {
        "interpretation": "current_rule_contract_consistency_only",
        "not_a_claim_of": "real_world_predictive_accuracy_or_scientific_validity",
        "foundation_leaders": leader_ids,
        "models": models_summary,
    }


def run(output: Path, dry_run: bool = False, retry_schema_invalid: bool = False) -> dict:
    config = load_config()
    questions = build_question_bank(config)
    state = _load_checkpoint(output, config, questions)
    if dry_run:
        return {
            "config_hash": state["config_hash"],
            "question_bank_hash": state["question_bank_hash"],
            "question_count": len(questions),
            "category_counts": config["categories"],
            "model_blind_map": state["model_blind_map"],
        }

    prompt = (HERE / "request-system.txt").read_text(encoding="utf-8").strip()
    batch_size = int(config["batch_size"])
    blind_ids = sorted(state["model_blind_map"])
    for repetition in range(int(config["repetitions"])):
        materialized = {
            blind_id: materialize_questions(questions, config, blind_id, repetition)
            for blind_id in blind_ids
        }
        batch_count = len(questions) // batch_size
        for batch_number in range(batch_count):
            offset = (repetition + batch_number) % len(blind_ids)
            order = blind_ids[offset:] + blind_ids[:offset]
            for blind_id in order:
                key = _batch_key(repetition, batch_number)
                existing = state.get("runs", {}).get(blind_id, {}).get(key)
                if (
                    existing
                    and existing.get("status") == "success"
                    and not (retry_schema_invalid and not existing.get("schema_valid"))
                ):
                    continue
                model = state["model_blind_map"][blind_id]
                start = batch_number * batch_size
                items = materialized[blind_id][start:start + batch_size]
                request = json.dumps({
                    "schema_version": "four-model-foundation-questions-v1",
                    "questions": public_batch(items),
                }, ensure_ascii=False, separators=(",", ":"))
                print(f"[{blind_id}] 第 {repetition + 1} 轮 / 第 {batch_number + 1} 批...", flush=True)
                started = time.monotonic()
                try:
                    # DeepSeek V4 Pro may spend most of a 6k completion budget on
                    # internal reasoning and return no final JSON. Give it enough
                    # headroom; the scored answer is still only 15 choice letters.
                    max_tokens = 12000 if model["provider"] == "deepseek" else 6000
                    response = gateway.call(
                        model["provider"], model["model_id"], prompt, request,
                        max_tokens=max_tokens, temperature=-1,
                        output_schema_version="four-model-foundation-answers-v1",
                    )
                    answer_map, schema_valid, schema_errors = parse_answers(
                        response["text"], [item["id"] for item in items]
                    )
                    decoded = {
                        qid: next(item["options"][choice] for item in items if item["id"] == qid)
                        for qid, choice in answer_map.items()
                    }
                    record = {
                        "status": "success",
                        "schema_valid": schema_valid,
                        "schema_errors": schema_errors,
                        "decoded_answers": decoded,
                        "latency_seconds": round(time.monotonic() - started, 3),
                        "token_usage": response.get("token_usage", {}),
                        "run_id": response.get("run_id"),
                    }
                except Exception as exc:  # checkpoint the provider failure; resume retries it
                    record = {
                        "status": "api_error",
                        "error_type": exc.__class__.__name__,
                        "error": str(exc)[:300],
                        "latency_seconds": round(time.monotonic() - started, 3),
                    }
                state.setdefault("runs", {}).setdefault(blind_id, {})[key] = record
                state["summary"] = summarize(state, config, questions)
                _save_checkpoint(output, state)
                print(
                    f"  {record['status']} / {record.get('latency_seconds', 0):.1f}s"
                    + (f" / schema={record.get('schema_valid')}" if record["status"] == "success" else ""),
                    flush=True,
                )

    state["summary"] = summarize(state, config, questions)
    _save_checkpoint(output, state)
    return state


def main() -> int:
    parser = argparse.ArgumentParser(description="四模型八字基础规则盲测")
    parser.add_argument(
        "--out", type=Path,
        default=ROOT / "evals" / "reports" / "four-model-bakeoff.json",
        help="断点结果文件（默认位于 gitignored evals/reports）",
    )
    parser.add_argument("--dry-run", action="store_true", help="只校验并显示冻结配置，不调用 API")
    parser.add_argument(
        "--retry-schema-invalid", action="store_true",
        help="断点续跑时只额外重试先前 API 成功但格式不合规的批次",
    )
    args = parser.parse_args()
    result = run(
        args.out.resolve(), dry_run=args.dry_run,
        retry_schema_invalid=args.retry_schema_invalid,
    )
    if args.dry_run:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    summary = result["summary"]
    print("\n基础规则一致性结果（不等于真实预测准确率）：")
    rows = sorted(
        summary["models"].items(),
        key=lambda pair: (-pair[1]["exact_choice_accuracy"], pair[0]),
    )
    for blind_id, row in rows:
        status = "可排名" if row["ranking_eligible"] else "未完成，不排名"
        print(
            f"- {blind_id} {row['family']} / {row['model_id']}: "
            f"{row['correct']}/{row['expected_answers']} "
            f"({row['exact_choice_accuracy']:.1%}), 稳定率 {row['cross_repeat_stability']:.1%}, {status}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
