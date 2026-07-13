//! 对拍 CLI：stdin JSONL → stdout JSONL（协议见 paipan-spec 附录 A）。
//!
//! 单行解析/输入错误 → 该行输出 `ok:false`，进程继续处理后续行，不崩溃。

use std::io::{self, BufRead, Write};

use serde::Deserialize;
use serde_json::{json, Value};

#[derive(Deserialize)]
struct CaseLine {
    case_id: String,
    op: String,
    input: Value,
}

#[derive(Deserialize)]
struct YearPillarInput {
    civil_year: i32,
    t_unix: i64,
    lichun_unix: i64,
}

#[derive(Deserialize)]
struct LocalIn {
    y: i32,
    m: u8,
    d: u8,
    hh: u8,
    mm: u8,
    ss: u8,
}

#[derive(Deserialize)]
struct MonthCtxIn {
    jie_seq: u8,
    jie_unix: i64,
    next_jie_unix: i64,
}

#[derive(Deserialize)]
struct FourPillarsInput {
    t_unix: i64,
    lichun_unix: i64,
    local: LocalIn,
    month_ctx: MonthCtxIn,
    zi_hour_mode: String,
}

#[derive(Deserialize)]
struct UncertaintyInput {
    t_unix: i64,
    lichun_unix: i64,
    local: LocalIn,
    month_ctx: MonthCtxIn,
    zi_hour_mode: String,
    input_time_precision_seconds: i64,
}

fn pillar_json(gz: engine_paipan::ganzhi::GanZhi) -> Value {
    json!({"stem": gz.stem_name(), "branch": gz.branch_name(), "ganzhi": gz.name()})
}

fn four_pillars_uncertainty_response(case_id: &str, input: Value) -> Value {
    let inp: UncertaintyInput = match serde_json::from_value(input.clone()) {
        Ok(v) => v,
        Err(e) => {
            return json!({"case_id": case_id, "ok": false, "error": format!("bad input: {e}")});
        }
    };
    if inp.input_time_precision_seconds < 0 {
        return json!({"case_id": case_id, "ok": false,
            "error": "negative input_time_precision_seconds (AMB)"});
    }
    // 复用 four_pillars 的全部校验与计算(spec 4.5:其余校验与错误路径同 4.4)
    let mut base = four_pillars_response(case_id, input);
    if base.get("ok") != Some(&Value::Bool(true)) {
        return base;
    }
    let mode = match inp.zi_hour_mode.as_str() {
        "split" => engine_paipan::four_pillars::ZiHourMode::Split,
        _ => engine_paipan::four_pillars::ZiHourMode::Unified,
    };
    let local = engine_paipan::four_pillars::LocalTime {
        y: inp.local.y,
        m: inp.local.m,
        d: inp.local.d,
        hh: inp.local.hh,
        mm: inp.local.mm,
        ss: inp.local.ss,
    };
    let ctx = engine_paipan::four_pillars::MonthCtx {
        jie_seq: inp.month_ctx.jie_seq,
        jie_unix: inp.month_ctx.jie_unix,
        next_jie_unix: inp.month_ctx.next_jie_unix,
    };
    let unc = engine_paipan::four_pillars::uncertainty(
        inp.t_unix,
        inp.lichun_unix,
        local,
        ctx,
        mode,
        inp.input_time_precision_seconds,
    );
    if let Some(out) = base.get_mut("output").and_then(Value::as_object_mut) {
        out.insert(
            "result_status".to_string(),
            json!(if unc.ambiguous { "ambiguous" } else { "exact" }),
        );
        out.insert(
            "boundary_distance_seconds".to_string(),
            json!(unc.boundary_distance_seconds),
        );
        out.insert("uncertainty_sources".to_string(), json!(unc.sources));
    }
    base
}

fn four_pillars_response(case_id: &str, input: Value) -> Value {
    let inp: FourPillarsInput = match serde_json::from_value(input) {
        Ok(v) => v,
        Err(e) => {
            return json!({"case_id": case_id, "ok": false, "error": format!("bad input: {e}")});
        }
    };
    let mode = match inp.zi_hour_mode.as_str() {
        "split" => engine_paipan::four_pillars::ZiHourMode::Split,
        "unified" => engine_paipan::four_pillars::ZiHourMode::Unified,
        other => {
            return json!({"case_id": case_id, "ok": false,
                "error": format!("bad zi_hour_mode: {other}")});
        }
    };
    let local = engine_paipan::four_pillars::LocalTime {
        y: inp.local.y,
        m: inp.local.m,
        d: inp.local.d,
        hh: inp.local.hh,
        mm: inp.local.mm,
        ss: inp.local.ss,
    };
    let ctx = engine_paipan::four_pillars::MonthCtx {
        jie_seq: inp.month_ctx.jie_seq,
        jie_unix: inp.month_ctx.jie_unix,
        next_jie_unix: inp.month_ctx.next_jie_unix,
    };
    match engine_paipan::four_pillars::four_pillars(inp.t_unix, inp.lichun_unix, local, ctx, mode) {
        Ok(fp) => json!({"case_id": case_id, "ok": true, "output": {
            "bazi_year": fp.bazi_year,
            "year": pillar_json(fp.year),
            "month": pillar_json(fp.month),
            "day": pillar_json(fp.day),
            "hour": pillar_json(fp.hour),
        }}),
        Err(e) => json!({"case_id": case_id, "ok": false, "error": e}),
    }
}

fn year_pillar_response(case_id: &str, input: Value) -> Value {
    match serde_json::from_value::<YearPillarInput>(input) {
        Ok(inp) => {
            let yp = engine_paipan::year_pillar::year_pillar(
                inp.civil_year,
                inp.t_unix,
                inp.lichun_unix,
            );
            json!({
                "case_id": case_id,
                "ok": true,
                "output": {
                    "bazi_year": yp.bazi_year,
                    "stem": yp.ganzhi.stem_name(),
                    "branch": yp.ganzhi.branch_name(),
                    "ganzhi": yp.ganzhi.name(),
                }
            })
        }
        Err(e) => json!({"case_id": case_id, "ok": false, "error": format!("bad input: {e}")}),
    }
}

fn handle_line(line: &str) -> Value {
    let case: CaseLine = match serde_json::from_str(line) {
        Ok(c) => c,
        Err(e) => {
            return json!({"case_id": null, "ok": false, "error": format!("bad case line: {e}")});
        }
    };
    match case.op.as_str() {
        "year_pillar" => year_pillar_response(&case.case_id, case.input),
        "four_pillars" => four_pillars_response(&case.case_id, case.input),
        "four_pillars_uncertainty" => four_pillars_uncertainty_response(&case.case_id, case.input),
        other => {
            json!({"case_id": case.case_id, "ok": false, "error": format!("unknown op: {other}")})
        }
    }
}

fn main() -> io::Result<()> {
    let stdin = io::stdin();
    let mut out = io::stdout().lock();
    for line in stdin.lock().lines() {
        let line = line?;
        if line.trim().is_empty() {
            continue;
        }
        writeln!(out, "{}", handle_line(&line))?;
    }
    Ok(())
}
