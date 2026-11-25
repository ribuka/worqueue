// Shows one task in the side panel and sends its edits, history entries, and completion.

import { doneTask, editTask, getTask, logTask } from "./api.js";

const HISTORY_HEADING = "## 履歴";

// Returns the history of a task's Markdown: the lines after the history heading line, trimmed, or "" without one.
export function historyOf(markdown) {
  const lines = markdown.split("\n");
  const at = lines.indexOf(HISTORY_HEADING);
  return at < 0 ? "" : lines.slice(at + 1).join("\n").trim();
}

// Returns the IDs written in the dependencies field ("3, 5"), or null if a part is not an ID.
export function parseDependencies(text) {
  const parts = text.split(",").map((part) => part.trim()).filter((part) => part !== "");
  if (!parts.every((part) => /^\d+$/.test(part))) return null;
  return parts.map(Number);
}

// Returns the fields of `values` that differ from `initial`, comparing lists by their items.
export function changedFields(initial, values) {
  const changed = {};
  for (const [name, value] of Object.entries(values)) {
    if (JSON.stringify(value) !== JSON.stringify(initial[name])) changed[name] = value;
  }
  return changed;
}

// Returns the panel's controller: open(id), reload(), close(), and the forms' handlers.
// `run(action)` runs a write and refreshes the page; it is given by app.js.
export function createDetail(run) {
  const panel = document.getElementById("detail");
  const field = (id) => document.getElementById(id);
  let current = null; // {id, version, initial}
  // Counts opens and closes: a response read for an earlier one is dropped.
  let generation = 0;

  // Shows the task in the panel, keeping nothing typed before; does nothing if
  // another task was opened, or the panel closed, while it was being read.
  async function open(id) {
    const mine = ++generation;
    const { task, body, version } = await getTask(id);
    if (mine !== generation) return;
    if (task.status === "done") {
      close();
      return;
    }
    const initial = {
      title: task.title,
      status: task.status,
      kind: task.kind,
      assignee: task.assignee,
      due: task.due,
      depends_on: task.depends_on,
      body,
    };
    current = { id, version, initial };
    field("detail-title").textContent = `${task.id} ${task.title}`;
    field("edit-title").value = task.title;
    field("edit-status").value = task.status;
    field("edit-kind").value = task.kind;
    field("edit-assignee").value = task.assignee;
    field("edit-due").value = task.due ?? "";
    field("edit-depends-on").value = task.depends_on.join(", ");
    field("edit-body").value = body;
    field("edit-reason").value = "";
    field("history").textContent = historyOf(task.markdown);
    field("log-content").value = "";
    field("done-reason").value = "";
    panel.hidden = false;
  }

  // Hides the panel.
  function close() {
    generation++;
    current = null;
    panel.hidden = true;
  }

  // Sends the fields changed from when the task was opened; sends nothing if none changed.
  function save() {
    const dependsOn = parseDependencies(field("edit-depends-on").value);
    if (dependsOn === null) throw new Error("依存先は , 区切りの ID にしてください");
    const values = {
      title: field("edit-title").value,
      status: field("edit-status").value,
      kind: field("edit-kind").value,
      assignee: field("edit-assignee").value,
      due: field("edit-due").value || null,
      depends_on: dependsOn,
      body: field("edit-body").value,
    };
    const changed = changedFields(current.initial, values);
    if (Object.keys(changed).length === 0) return Promise.resolve();
    const reason = field("edit-reason").value.trim();
    return editTask(current.id, { version: current.version, ...changed, ...(reason ? { reason } : {}) });
  }

  field("edit-form").addEventListener("submit", (event) => {
    event.preventDefault();
    run(save);
  });
  field("log-form").addEventListener("submit", (event) => {
    event.preventDefault();
    run(() => logTask(current.id, current.version, field("log-content").value));
  });
  field("done-form").addEventListener("submit", (event) => {
    event.preventDefault();
    run(async () => {
      await doneTask(current.id, current.version, field("done-reason").value.trim());
      close();
    });
  });
  field("detail-close").addEventListener("click", close);

  return {
    open,
    close,
    // Reads the open task again (discarding what was typed); does nothing when closed.
    reload: () => (current === null ? Promise.resolve() : open(current.id)),
  };
}
