// Luồng agent của một câu trả lời: câu hỏi → từng node (input/output) → câu trả lời.
// Dữ liệu (`props`) do `co5151_web.present.flow_props` dựng từ GET /traces/{id}/spans; file này chỉ hiển thị.
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Brain, Database, FileText, MessageSquare, PenLine, ShieldCheck, ChevronDown, ChevronRight } from "lucide-react";

const ICONS = {
  planner: Brain,
  student_record: Database,
  regulation: FileText,
  writer: PenLine,
  verifier: ShieldCheck,
};
const TONES = {
  ok: { dot: "#16a34a", text: "inherit" },
  warn: { dot: "#d97706", text: "#b45309" },
  error: { dot: "#dc2626", text: "#dc2626" },
};

function Json({ title, text }) {
  return (
    <div style={{ marginTop: 6 }}>
      <div className="text-xs font-medium text-muted-foreground">{title}</div>
      <pre
        className="text-xs rounded-md border"
        style={{ margin: "2px 0 0", padding: 8, maxHeight: 260, overflow: "auto", whiteSpace: "pre-wrap", wordBreak: "break-word" }}
      >
        {text}
      </pre>
    </div>
  );
}

function Node({ node, last }) {
  const [open, setOpen] = useState(false);
  const Icon = ICONS[node.node] || MessageSquare;
  const tone = TONES[node.tone] || TONES.ok;
  const Chevron = open ? ChevronDown : ChevronRight;
  return (
    <div style={{ display: "flex", gap: 10 }}>
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", width: 28, flexShrink: 0 }}>
        <div className="rounded-full border" style={{ width: 28, height: 28, display: "flex", alignItems: "center", justifyContent: "center", position: "relative" }}>
          <Icon size={15} />
          <span style={{ position: "absolute", right: -2, top: -2, width: 9, height: 9, borderRadius: 9, background: tone.dot }} />
        </div>
        {!last && <div style={{ flex: 1, width: 2, minHeight: 14, background: "var(--border, #e5e7eb)" }} />}
      </div>
      <div style={{ flex: 1, minWidth: 0, paddingBottom: 12 }}>
        <button
          type="button"
          onClick={() => setOpen(!open)}
          style={{ all: "unset", cursor: "pointer", display: "block", width: "100%" }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
            <Chevron size={14} />
            <span className="text-sm font-medium">{node.label}</span>
            <Badge variant="outline">{node.name}</Badge>
            <span className="text-xs text-muted-foreground">
              {node.ms} ms{node.tokens ? ` · ${node.tokens} token` : ""}
            </span>
          </div>
          <div className="text-xs" style={{ marginTop: 2, marginLeft: 20, color: tone.text }}>
            {node.summary}
          </div>
        </button>
        {open && (
          <div style={{ marginLeft: 20 }}>
            <Json title="Input" text={node.input} />
            <Json title="Output" text={node.output} />
          </div>
        )}
      </div>
    </div>
  );
}

function Bubble({ title, text }) {
  return (
    <div className="rounded-md border" style={{ padding: 8, margin: "4px 0 12px" }}>
      <div className="text-xs font-medium text-muted-foreground">{title}</div>
      <div className="text-sm" style={{ whiteSpace: "pre-wrap", maxHeight: 160, overflow: "auto" }}>{text}</div>
    </div>
  );
}

// Ô chọn câu trả lời: gọi action `agent_flow` của app.py, server vẽ lại panel cho câu được chọn.
function Picker({ answers, selected }) {
  if (!answers || answers.length === 0) return null;
  return (
    <select
      className="text-sm rounded-md border"
      style={{ width: "100%", padding: "6px 8px", marginBottom: 10, background: "transparent", color: "inherit" }}
      value={selected || ""}
      onChange={(e) => e.target.value && callAction({ name: "agent_flow", payload: { trace_id: e.target.value } })}
    >
      {!selected && <option value="">Chọn câu trả lời để xem luồng…</option>}
      {answers.map((a) => (
        <option key={a.trace_id} value={a.trace_id}>{a.label}</option>
      ))}
    </select>
  );
}

export default function AgentFlow() {
  if (props.empty) {
    return (
      <div style={{ padding: 4 }}>
        <Picker answers={props.answers} selected={null} />
        <div className="text-sm text-muted-foreground">
          Gửi một câu hỏi, hoặc bấm "Luồng agent" dưới một câu trả lời, để xem từng node (Planner, MCP, Advisor,
          Verifier) đã nhận gì và trả về gì.
        </div>
      </div>
    );
  }
  const nodes = props.nodes || [];
  const totals = [
    props.total_ms != null ? `${(props.total_ms / 1000).toFixed(2)} s` : null,
    props.total_tokens ? `${props.total_tokens} token` : null,
    props.llm,
  ].filter(Boolean);
  return (
    <div style={{ padding: 4 }}>
      <Picker answers={props.answers} selected={props.selected} />
      {totals.length > 0 && <div className="text-xs text-muted-foreground" style={{ marginBottom: 8 }}>{totals.join(" · ")}</div>}
      <Bubble title="Câu hỏi" text={props.question} />
      {nodes.length === 0 && <div className="text-sm text-muted-foreground">Không có node nào được ghi lại.</div>}
      {nodes.map((node, i) => (
        <Node key={node.id} node={node} last={i === nodes.length - 1} />
      ))}
      <Bubble title="Câu trả lời gửi cho sinh viên" text={props.answer || "(không có câu trả lời — xem lỗi ở các node)"} />
    </div>
  );
}
