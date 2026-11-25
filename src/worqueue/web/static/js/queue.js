// Draws the queue table and the count and ratio of the kinds, and reports drops of a row on another.

const KIND_LABELS = { manage: "管理", implement: "実装" };

// Returns the label of a kind (管理 or 実装).
export function kindLabel(kind) {
  return KIND_LABELS[kind] ?? kind;
}

// Returns the text of the ratio of manage to implement tasks, e.g. "管理 1（33%） / 実装 2（67%）".
export function ratioText(tasks) {
  const manage = tasks.filter((t) => t.kind === "manage").length;
  const implement = tasks.filter((t) => t.kind === "implement").length;
  const total = manage + implement;
  if (total === 0) return "管理 0 / 実装 0";
  const percent = (n) => Math.round((n / total) * 100);
  return `管理 ${manage}（${percent(manage)}%） / 実装 ${implement}（${percent(implement)}%）`;
}

// Returns the ID to put the dragged task before (null for the bottom), or undefined when it would not move.
// `place` is the index in `tasks` before which the row was dropped (tasks.length for after the last).
export function moveTarget(tasks, draggedId, place) {
  const from = tasks.findIndex((t) => t.id === draggedId);
  if (from < 0 || place === from || place === from + 1) return undefined;
  return place < tasks.length ? tasks[place].id : null;
}

// Fills the table body with one row per task. `onOpen(id)` runs on a click, `onMove(id, before)` on a drop.
export function renderQueue(tbody, tasks, { onOpen, onMove }) {
  tbody.replaceChildren(...tasks.map((task, index) => row(task, index, tasks, { onOpen, onMove })));
}

// Returns one row: its cells, its click, and its drag and drop.
function row(task, index, tasks, { onOpen, onMove }) {
  const tr = document.createElement("tr");
  tr.dataset.id = String(task.id);
  tr.draggable = true;
  const cells = [task.position, task.id, task.title, task.status, kindLabel(task.kind), task.assignee, task.due ?? "-"];
  for (const value of cells) {
    const td = document.createElement("td");
    td.textContent = String(value);
    tr.append(td);
  }
  tr.querySelector("td:nth-child(4)").className = `status status-${task.status}`;
  tr.addEventListener("click", () => onOpen(task.id));
  tr.addEventListener("dragstart", (event) => {
    event.dataTransfer.setData("text/plain", String(task.id));
    event.dataTransfer.effectAllowed = "move";
  });
  tr.addEventListener("dragover", (event) => {
    event.preventDefault();
    const upper = isUpperHalf(tr, event);
    tr.classList.toggle("drop-before", upper);
    tr.classList.toggle("drop-after", !upper);
  });
  tr.addEventListener("dragleave", () => tr.classList.remove("drop-before", "drop-after"));
  tr.addEventListener("drop", (event) => {
    event.preventDefault();
    tr.classList.remove("drop-before", "drop-after");
    const dragged = Number(event.dataTransfer.getData("text/plain"));
    const before = moveTarget(tasks, dragged, isUpperHalf(tr, event) ? index : index + 1);
    if (before !== undefined) onMove(dragged, before);
  });
  return tr;
}

// Returns whether the pointer of a drag event is in the upper half of the row.
function isUpperHalf(tr, event) {
  const rect = tr.getBoundingClientRect();
  return event.clientY < rect.top + rect.height / 2;
}
