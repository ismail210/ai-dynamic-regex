/* Estima3D A2/A7 human review — validation UI only */

const state = {
  mode: "a2",
  a2: null,
  a7: null,
  index: 0,
  filter: "all",
  dirty: false,
};

const $ = (id) => document.getElementById(id);

function isA2Reviewed(row) {
  return Boolean(row?.human_review?.verdict);
}
function isA7Reviewed(link) {
  return Boolean(link?.human_review?.verdict);
}

function filteredItems() {
  if (state.mode === "a2") {
    const rows = state.a2?.rows || [];
    return rows
      .map((row, i) => ({ row, i }))
      .filter(({ row }) => {
        const hr = row.human_review || {};
        switch (state.filter) {
          case "unreviewed":
            return !isA2Reviewed(row);
          case "reviewed":
            return isA2Reviewed(row);
          case "ambiguous":
            return hr.verdict === "AMBIGUOUS" || hr.extraction_correct === "AMBIGUOUS";
          case "incorrect":
            return (
              hr.extraction_correct === "NO" ||
              hr.grouping_correct === "NO" ||
              hr.operation_correct === "NO" ||
              hr.reason_code === "extraction_error" ||
              hr.reason_code === "grouping_error" ||
              hr.reason_code === "normalization_error"
            );
          case "abstain":
            return hr.should_abstain === "YES" || hr.verdict === "ABSTAIN";
          default:
            return true;
        }
      });
  }
  const links = state.a7?.links || [];
  return links
    .map((row, i) => ({ row, i }))
    .filter(({ row }) => {
      const hr = row.human_review || {};
      switch (state.filter) {
        case "unreviewed":
          return !isA7Reviewed(row);
        case "reviewed":
          return isA7Reviewed(row);
        case "ambiguous":
          return hr.verdict === "AMBIGUOUS";
        case "incorrect":
          return hr.verdict === "WRONG";
        case "abstain":
          return false;
        default:
          return true;
      }
    });
}

function current() {
  const items = filteredItems();
  if (!items.length) return null;
  if (state.index >= items.length) state.index = items.length - 1;
  if (state.index < 0) state.index = 0;
  return items[state.index];
}

function choiceGroup(field, options, selected) {
  const wrap = document.createElement("div");
  wrap.className = "field";
  const label = document.createElement("label");
  label.textContent = field;
  wrap.appendChild(label);
  const choices = document.createElement("div");
  choices.className = "choices";
  options.forEach((opt) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = opt;
    if (selected === opt) btn.classList.add("selected");
    btn.addEventListener("click", () => {
      const cur = current();
      if (!cur) return;
      cur.row.human_review[field] = opt;
      if (state.mode === "a7" && field === "verdict") {
        cur.row.human_review.association_correct = opt;
      }
      cur.row.human_review.reviewed_at = new Date().toISOString();
      state.dirty = true;
      render();
    });
    choices.appendChild(btn);
  });
  // clear
  const clear = document.createElement("button");
  clear.type = "button";
  clear.textContent = "clear";
  clear.addEventListener("click", () => {
    const cur = current();
    if (!cur) return;
    cur.row.human_review[field] = null;
    if (state.mode === "a7" && field === "verdict") {
      cur.row.human_review.association_correct = null;
    }
    state.dirty = true;
    render();
  });
  choices.appendChild(clear);
  wrap.appendChild(choices);
  return wrap;
}

function textField(field, placeholder) {
  const wrap = document.createElement("div");
  wrap.className = "field";
  const label = document.createElement("label");
  label.textContent = field;
  wrap.appendChild(label);
  const input = document.createElement("input");
  input.type = "text";
  input.placeholder = placeholder || "";
  const cur = current();
  input.value = cur?.row?.human_review?.[field] ?? "";
  input.addEventListener("input", () => {
    const c = current();
    if (!c) return;
    const v = input.value.trim();
    c.row.human_review[field] = v === "" ? null : v;
    state.dirty = true;
  });
  wrap.appendChild(input);
  return wrap;
}

function render() {
  const items = filteredItems();
  const totalMode = state.mode === "a2" ? 70 : 100;
  const reviewedCount =
    state.mode === "a2"
      ? (state.a2?.rows || []).filter(isA2Reviewed).length
      : (state.a7?.links || []).filter(isA7Reviewed).length;
  $("counter").textContent = items.length
    ? `${state.index + 1} / ${items.length} filtered · ${reviewedCount} / ${totalMode} reviewed`
    : `0 / 0 filtered · ${reviewedCount} / ${totalMode} reviewed`;

  const cur = current();
  const ctx = $("context");
  const sys = $("system");
  const form = $("form");
  const bbox = $("bbox");
  form.innerHTML = "";
  if (!cur) {
    ctx.innerHTML = "<p>No rows match this filter.</p>";
    sys.textContent = "";
    bbox.textContent = "";
    return;
  }
  const row = cur.row;
  if (state.mode === "a2") {
    const refs = row.drawing_refs || {};
    ctx.innerHTML = `
      <dt>review_id</dt><dd>${row.review_id}</dd>
      <dt>document</dt><dd>${row.document || ""} (${row.document_id || ""})</dd>
      <dt>source page</dt><dd>${row.page ?? ""}</dd>
      <dt>extract page</dt><dd>${row.extract_page ?? ""}</dd>
      <dt>raw_text</dt><dd><strong>${escapeHtml(row.raw_text || "")}</strong></dd>
      <dt>extract PDF</dt><dd>${refs.extract_pdf || "—"}</dd>
      <dt>full PDF</dt><dd>${refs.full_pdf || "—"}</dd>
      <dt>annotation</dt><dd>${row.source_annotation_id || ""}</dd>
      <dt>gold_id</dt><dd>${row.source_gold_id || ""}</dd>
    `;
    bbox.textContent = JSON.stringify(
      { label_bbox: refs.label_bbox, fragments_gold: row.fragments_gold, group_id_gold: row.group_id_gold },
      null,
      2
    );
    sys.textContent = JSON.stringify(row.system, null, 2);
    const enums = state.a2.enums;
    form.appendChild(choiceGroup("extraction_correct", enums.extraction_correct, row.human_review.extraction_correct));
    form.appendChild(choiceGroup("grouping_correct", enums.grouping_correct, row.human_review.grouping_correct));
    form.appendChild(choiceGroup("operation_correct", enums.operation_correct, row.human_review.operation_correct));
    form.appendChild(choiceGroup("should_abstain", enums.should_abstain, row.human_review.should_abstain));
    form.appendChild(choiceGroup("verdict", enums.verdict, row.human_review.verdict));
    form.appendChild(choiceGroup("reason_code", enums.reason_code, row.human_review.reason_code));
    form.appendChild(textField("expected_normalized_value", "e.g. L4X4 or ABSTAIN_MISSING_THICKNESS"));
  } else {
    const refs = row.drawing_refs || {};
    ctx.innerHTML = `
      <dt>review_id</dt><dd>${row.review_id}</dd>
      <dt>document</dt><dd>${row.document || ""} (${row.document_id || ""})</dd>
      <dt>page</dt><dd>${row.page ?? ""}</dd>
      <dt>label</dt><dd><strong>${escapeHtml(row.label || "")}</strong></dd>
      <dt>method</dt><dd>${row.association_method || ""}</dd>
      <dt>candidate geom</dt><dd>${row.candidate_geometry_id || "—"} (${row.candidate_geometry_kind || "—"})</dd>
      <dt>extract PDF</dt><dd>${refs.extract_pdf || "—"}</dd>
      <dt>full PDF</dt><dd>${refs.full_pdf || "—"}</dd>
      <dt>rule</dt><dd>Is this the structural member the annotation describes? (not merely nearest line)</dd>
    `;
    bbox.textContent = JSON.stringify(
      {
        label_bbox: row.label_bbox,
        candidate_geometry_bbox: row.candidate_geometry_bbox,
        system_confidence: row.system_confidence,
      },
      null,
      2
    );
    sys.textContent = JSON.stringify(
      {
        association_method: row.association_method,
        candidate_geometry_id: row.candidate_geometry_id,
        candidate_geometry_kind: row.candidate_geometry_kind,
        system_confidence: row.system_confidence,
      },
      null,
      2
    );
    const enums = state.a7.enums;
    form.appendChild(choiceGroup("verdict", enums.verdict, row.human_review.verdict));
    form.appendChild(choiceGroup("reason_code", enums.reason_code, row.human_review.reason_code));
    form.appendChild(textField("target_geometry_id", "optional correct geometry id"));
  }
  $("notes").value = row.human_review.notes || "";
  $("reviewed_by").value = row.human_review.reviewed_by || "";
  $("status").textContent = state.dirty ? "Unsaved changes" : "Saved / clean";
}

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

async function loadAll() {
  const [a2, a7] = await Promise.all([
    fetch("/api/a2").then((r) => r.json()),
    fetch("/api/a7").then((r) => r.json()),
  ]);
  state.a2 = a2;
  state.a7 = a7;
  state.index = 0;
  render();
}

async function save() {
  const cur = current();
  if (cur) {
    cur.row.human_review.notes = $("notes").value || "";
    cur.row.human_review.reviewed_by = $("reviewed_by").value || "";
    if (cur.row.human_review.verdict && !cur.row.human_review.reviewed_at) {
      cur.row.human_review.reviewed_at = new Date().toISOString();
    }
  }
  // update reviewed_count
  if (state.mode === "a2") {
    state.a2.reviewed_count = (state.a2.rows || []).filter(isA2Reviewed).length;
    const res = await fetch("/api/a2", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(state.a2),
    });
    const body = await res.json();
    $("status").textContent = body.ok ? `Saved A2 → ${body.saved}` : `Save failed: ${body.error}`;
  } else {
    state.a7.reviewed_count = (state.a7.links || []).filter(isA7Reviewed).length;
    const res = await fetch("/api/a7", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(state.a7),
    });
    const body = await res.json();
    $("status").textContent = body.ok ? `Saved A7 → ${body.saved}` : `Save failed: ${body.error}`;
  }
  state.dirty = false;
  render();
}

$("mode-a2").addEventListener("click", () => {
  state.mode = "a2";
  state.index = 0;
  $("mode-a2").classList.add("active");
  $("mode-a7").classList.remove("active");
  render();
});
$("mode-a7").addEventListener("click", () => {
  state.mode = "a7";
  state.index = 0;
  $("mode-a7").classList.add("active");
  $("mode-a2").classList.remove("active");
  render();
});
$("prev").addEventListener("click", () => {
  const cur = current();
  if (cur) {
    cur.row.human_review.notes = $("notes").value || "";
    cur.row.human_review.reviewed_by = $("reviewed_by").value || "";
  }
  state.index = Math.max(0, state.index - 1);
  render();
});
$("next").addEventListener("click", () => {
  const cur = current();
  if (cur) {
    cur.row.human_review.notes = $("notes").value || "";
    cur.row.human_review.reviewed_by = $("reviewed_by").value || "";
  }
  state.index = Math.min(filteredItems().length - 1, state.index + 1);
  render();
});
$("filter").addEventListener("change", (e) => {
  state.filter = e.target.value;
  state.index = 0;
  render();
});
$("save").addEventListener("click", () => save());
$("notes").addEventListener("input", () => {
  const cur = current();
  if (!cur) return;
  cur.row.human_review.notes = $("notes").value || "";
  state.dirty = true;
});
$("reviewed_by").addEventListener("input", () => {
  const cur = current();
  if (!cur) return;
  cur.row.human_review.reviewed_by = $("reviewed_by").value || "";
  state.dirty = true;
});

loadAll().catch((err) => {
  $("status").textContent = `Load failed: ${err}. Start scripts/serve_human_review.py`;
});
