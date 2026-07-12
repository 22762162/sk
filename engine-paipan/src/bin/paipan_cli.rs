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
