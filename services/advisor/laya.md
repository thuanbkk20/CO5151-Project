Try it locally: web GUI + JSON API
examples/server.py is a self-contained FastAPI app for testing Laya without writing any code: a two-pane playground (edit the request as a form or as JSON, run it with Ctrl+Enter, read each answer's full distribution and calibrated confidence, copy it as curl or Python), plus a plain JSON API (/predict, /predict/batch) for scripting against.

pip install "laya[serve]"
python examples/server.py               # http://127.0.0.1:8000
On Windows, start.bat does the same from a clone: it creates .venv with whichever supported Python is installed, installs CPU torch and the serve extra on first run, then starts the server and opens the browser. start.bat 8080 picks a different port.

Open http://127.0.0.1:8000 in a browser for the playground, or hit it directly:

curl -s localhost:8000/predict -H 'content-type: application/json' -d '{
  "state": {"body": "We were billed twice for March. Please refund it today."},
  "questions": {
    "department": {"type": "choice",
                   "instructions": "Which department should handle this?",
                   "criteria": {"billing": "invoices, payments, refunds", "other": "everything else"}},
    "urgency": {"type": "score",
                "instructions": "How urgent is this?",
                "criteria": ["not urgent", "soon", "critical"]}
  }
}' | python -m json.tool
--no-preload loads checkpoints lazily instead of all three up front; --device cuda|cpu|mps pins the device. See python examples/server.py --help for the rest.

A request body may carry model to pin a checkpoint instead of letting the router choose, and it takes exactly the spellings laya --model takes: names, aliases and casing all resolve through laya.router. GET /models lists the checkpoints and the aliases alongside them.

Both /predict and /predict/batch also accept the four per-call controls laya-serve forwards on /v1/systemone: lang_guess (a soft ISO hint that participates in routing, where lang skips detection entirely), max_len and head_max_len (per-call token-budget overrides, capped by LAYA_MAX_TOKEN_BUDGET), and min_confidence (core's abstention threshold; the answer comes back with abstention and abstention_threshold fields naming whether it fired). An absent key means "inherit what the Router was built with", so a caller never has to send them back as null; a body that names hooks, hooks_raise, hooks_timeout, on_predict_start, or on_predict_end is refused with 422 rather than silently dropped, matching what laya-serve does for the same fields. On /predict/batch the controls are read once, from the batch body: min_confidence becomes a call argument to Router.predict_batch, and the other three are copied into every request dict, so all states in one call share one budget. A max_len written inside a state is not a control there -- it stays part of the state, and the body's value is what every state gets. Per-request budgets do exist one level down, in Router.predict_batch, which cannot share a forward pass between requests naming different budgets and so makes one pass per budget; the batch endpoint just gives an HTTP caller no way to name them separately.

/predict/batch accepts two optional body fields that control the shape of the forward passes without changing any answer: batch_size (states per pass; omit it and the whole batch is one pass) and sort_by_length (group similarly sized states so each pass pads to a shorter maximum — it needs a batch_size below the number of states, since one pass has nothing to reorder). Measured on the running server: 64 real reviews of 91–2,293 characters, one choice question, batch_size: 8, three interleaved rounds on MPS — the default one-pass shape 5.35s median against 3.04s sorted, a paired median of 1.77x (min 1.76x), and 64/64 labels identical in input order. batch_size: 8 on its own was 4.95s, so the length grouping is what earns the second factor: 1.66x over the sized batch.

Python HTTP client
Applications that call a separate laya-serve can use the Python HTTP client without installing the inference dependencies. It provides synchronous predict() and health() calls using the standard library. From this checkout, install it with python -m pip install ./sdk/python in the application environment; keep laya[serve] in the server environment. The separate laya-client distribution is not yet published to PyPI.

JavaScript / TypeScript
laya-client supports JavaScript and TypeScript applications over HTTP to a self-hosted laya-serve /v1/systemone server. It includes inferred answer types, all five question presets, ESM/CommonJS exports, and cancellation.

# From this checkout, install and start the Python inference service:
pip install -e '.[serve]'
LAYA_HOST=127.0.0.1 LAYA_MODELS=english laya-serve

# In another terminal:
cd sdk/typescript
npm ci
npm run build
node examples/triage.mjs
The npm package is named laya-client. Use it when a JavaScript or TypeScript application talks over HTTP to self-hosted Python laya-serve. Use laya-ts when inference must run directly inside JavaScript through its local ONNX runtime, without a Python server. See installation, examples, and publishing and the repository analysis for architecture and scope.

Quickstart: Route Mode (Recommended)
To try the Python SDK in a CPU container, see the Docker Compose quickstart. It runs a sample request and keeps downloaded models between runs.

Laya ships three checkpoints. The built-in Router is the recommended entry point: it evaluates any state in any language, automatically detects scripts and languages in sub-milliseconds, and dispatches to the optimal checkpoint in a single forward pass.

Minimal example (30 seconds)
from laya import Router

router = Router()  # downloads only the selected checkpoint on first use
result = router.predict(
    {"body": "We were billed twice. Please refund the duplicate."},
    {"billing": {"type": "noul", "instructions": "Does the user request a refund?"}},
)
print(result["answers"]["billing"]["noul"])  # P(true), a float from 0.0 to 1.0
print(result["routing"]["model"])            # which checkpoint answered, e.g. 'english'
Input is any state (str, dict, or list — text, email, ticket, JSON document) plus a dict of typed questions (choice = pick one label, score = ordinal levels, noul = yes/no statement check). Each result["answers"][qid] is an answer dict: choice is the selected label, score is the expected ordinal level, and noul is P(true). confidence is a separate field in that dict; probabilities is available for choice and score. result["routing"] explains which checkpoint was picked and why. Values depend on the checkpoint and input. For ready-made question sets see laya.presets (triage_questions, moderation_questions, email_questions, ...).

Full walkthrough:

from laya import Router

# Preload checkpoints into memory for instant sub-35ms routing
router = Router(preload=True)

# 1. State in any language or schema
state = {
    "from": "user@acme.com",
    "subject": "Duplicate charge on invoice #4411",
    "body": "Hi, we were billed twice for March. Please refund the duplicate today or we will cancel our plan."
}

# 2. Define your typed questions
questions = {
    "department": {
        "type": "choice",
        "instructions": "Which department should handle this request?",
        "criteria": {
            "billing": "invoices, payments, refunds",
            "technical": "bugs, outages, system errors",
            "sales": "pricing, new contracts, plan upgrades",
            "other": "everything else"
        }
    },
    "urgency": {
        "type": "score",
        "instructions": "How urgent is this request?",
        "criteria": ["not urgent", "soon", "critical deadline or blocking issue"]
    },
    "churn_risk": {
        "type": "noul",
        "instructions": "Does the user threaten to cancel or leave?"
    },
    "refund_requested": {
        "type": "noul",
        "instructions": "Does the user explicitly request a refund?"
    }
}

# 3. English state -> automatically routed to laya (ModernBERT-large, 39.5 ms)
res_en = router.predict(state, questions)
print("Department :", res_en["answers"]["department"]["choice"])  # -> billing (confidence: 0.94)
print("Routing    :", res_en["routing"]["model"])                 # -> english

# 4. Hindi state -> automatically routed to laya-multilingual (mmBERT-base, 32.8 ms)
res_hi = router.predict({"body": "मुझसे दो बार शुल्क लिया गया, कृपया पैसे वापस करें।"}, questions)
print("Department :", res_hi["answers"]["department"]["choice"])  # -> billing (confidence: 0.86)
print("Routing    :", res_hi["routing"]["model"])                 # -> multilingual

# 5. Explicit override when you want a specific checkpoint
res_td = router.predict(state, questions, model="typed-decisions")
Every result carries full routing metadata explaining why the choice was made:

res_hi["routing"]
# {
#   'model': 'multilingual',
#   'repo': 'convaiinnovations/laya/multilingual',
#   'reason': 'non-Latin script (devanagari, 100% of letters); the English checkpoint cannot read it',
#   'detection': {'script': 'devanagari', 'script_profile': {'devanagari': 1.0},
#                 'language': None, 'is_english': False, 'language_undecided': True,
#                 'diacritic_rate': 0.0, 'non_latin_fraction': 1.0, 'mixed_segment': None},
#   'workflow': None
# }
All five keys are always present. detection is the laya.lang.analyse result the decision was made from, and is None whenever routing decided before detection ran: model=, task=, a detected workflow, a decisive lang= and a resolving lang_guess all take precedence over it and short-circuit it. workflow names the typed-decisions workflow whose question ids matched, and is None when none did.

Inspect a routing decision without running any forward pass:

router.route({"body": "Der Kunde wurde zweimal belastet"}, questions).reason
# "Latin script but language looks like 'de', not English"
Very short Latin-script text often carries nothing that identifies its language ("Quero cancelar", "Esqueci minha senha"). Such text goes to default, which is "multilingual" since 0.4.0. Text the detector can place is unaffected: identified English still goes to the English checkpoint.

router = Router()                                                   # default="multilingual"
router.route({"body": "Esqueci minha senha"}).model                 # -> multilingual
router.route({"body": "Please refund the duplicate charge"}).model  # -> english
If most of your traffic is English, set it back. The English checkpoint scores 0.820 on English against the multilingual checkpoint's 0.710, and the break-even is around 62% English traffic:

router = Router(default="english")
Running one of the shipped servers rather than your own Router, the same setting is LAYA_DEFAULT_MODEL=english — in the environment of laya-serve, the MCP server or the laya-serve container (docs/docker.md). It is the routing fallback only: text the detector can place is routed on what it detects, whatever this is set to.

example my macos:
Trạng thái hiện tại:
Process: Uvicorn server (Task ID: task-109, PID 93489)
Địa chỉ: http://0.0.0.0:8000 (Swagger UI: http://127.0.0.1:8000/docs)
Thiết bị tăng tốc: Apple GPU (device: mps)
Checkpoints sẵn sàng: english, multilingual, typed-decisions
Log phản hồi kiểm tra (curl http://127.0.0.1:8000/health):
http
HTTP/1.1 200 OK
server: uvicorn
content-type: application/json
{
  "status": "ok",
  "loaded": ["typed-decisions", "english", "multilingual"],
  "device": "mps",
  "checkpoint_devices": {
    "typed-decisions": "mps",
    "english": "mps",
    "multilingual": "mps"
  }
}
