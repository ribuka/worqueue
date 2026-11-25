// Draws the kanban board (one column per status) and turns drops of a card into a write:
// a move in the queue within a column, a status change between columns, or done.

import { kindLabel } from "./queue.js";

const DONE = "done";

// Returns the ID to put the dragged task before (null for the bottom of the queue), or undefined when it would
// not move. `tasks` is the queue from the top; `place` is the index in the column of `status` (the tasks of that
// status, in queue order) before which the card was dropped (the column's length for after its last card).
export function columnMoveTarget(tasks, status, draggedId, place) {
  const column = tasks.filter((t) => t.status === status);
  const from = column.findIndex((t) => t.id === draggedId);
  if (from < 0 || place === from || place === from + 1) return undefined;
  if (place < column.length) return column[place].id;
  // After the column's last card: before the task that follows it in the queue without the dragged one.
  const rest = tasks.filter((t) => t.id !== draggedId);
  const next = rest[rest.findIndex((t) => t.id === column[column.length - 1].id) + 1];
  return next === undefined ? null : next.id;
}

// Returns the write for a drop of task `draggedId` on the column of `status` at `place`, or null for none:
// {kind: "move", before}, {kind: "status", status}, or {kind: "done"}.
// `board` is {tasks, done}: the queue from the top, and the done tasks shown.
export function dropAction(board, draggedId, status, place) {
  const dragged = [...board.tasks, ...board.done].find((t) => t.id === draggedId);
  if (dragged === undefined) return null;
  if (dragged.status === status) {
    if (status === DONE) return null;
    const before = columnMoveTarget(board.tasks, status, draggedId, place);
    return before === undefined ? null : { kind: "move", before };
  }
  return status === DONE ? { kind: "done" } : { kind: "status", status };
}

// Wires the board's columns once and returns {render(board)}. `board` is what was read for one drawing:
// {tasks, done, doneTotal, queueVersion, taskVersions}. `onOpen(id)` runs on a click of a card not done,
// `onDrop(id, action, board)` on a drop that writes (see dropAction), with the board drawn when it was dropped,
// so the write carries the versions of the files as the cards show them.
export function createBoard(root, { onOpen, onDrop }) {
  let current = { tasks: [], done: [], doneTotal: 0, queueVersion: "none", taskVersions: {} };
  const columns = [...root.querySelectorAll(".column")];

  for (const column of columns) {
    const status = column.dataset.status;
    column.addEventListener("dragover", (event) => {
      event.preventDefault();
      showDropLine(column, placeOf(column, event));
    });
    column.addEventListener("dragleave", (event) => {
      if (!column.contains(event.relatedTarget)) clearDropLine(column);
    });
    column.addEventListener("drop", (event) => {
      event.preventDefault();
      clearDropLine(column);
      const dragged = Number(event.dataTransfer.getData("text/plain"));
      const action = dropAction(current, dragged, status, placeOf(column, event));
      if (action !== null) onDrop(dragged, action, current);
    });
  }

  function render(board) {
    current = board;
    for (const column of columns) {
      const status = column.dataset.status;
      const tasks = status === DONE ? board.done : board.tasks.filter((t) => t.status === status);
      column.querySelector(".column-count").textContent = String(status === DONE ? board.doneTotal : tasks.length);
      column.querySelector(".cards").replaceChildren(...tasks.map((task) => card(task, onOpen)));
      const more = column.querySelector(".more");
      if (more !== null) {
        const hidden = board.doneTotal - board.done.length;
        more.hidden = hidden <= 0;
        more.textContent = `ほか ${hidden} 件`;
      }
    }
  }

  return { render };
}

// Returns one card: its fields, its click (unless done), and its drag.
function card(task, onOpen) {
  const div = document.createElement("div");
  div.className = "card";
  div.dataset.id = String(task.id);
  div.draggable = true;
  const head = document.createElement("div");
  head.className = "card-head muted";
  head.textContent = task.position === null ? String(task.id) : `#${task.position}  ${task.id}`;
  const title = document.createElement("div");
  title.className = "card-title";
  title.textContent = task.title;
  const meta = document.createElement("div");
  meta.className = "card-meta muted";
  meta.textContent = [kindLabel(task.kind), task.assignee, task.due].filter((v) => v !== null).join(" · ");
  div.append(head, title, meta);
  if (task.status !== DONE) div.addEventListener("click", () => onOpen(task.id));
  div.addEventListener("dragstart", (event) => {
    event.dataTransfer.setData("text/plain", String(task.id));
    event.dataTransfer.effectAllowed = "move";
  });
  return div;
}

// Returns the index in the column before which a drop at the pointer goes: the number of cards whose middle is above it.
function placeOf(column, event) {
  const cards = [...column.querySelectorAll(".card")];
  return cards.filter((c) => {
    const rect = c.getBoundingClientRect();
    return rect.top + rect.height / 2 < event.clientY;
  }).length;
}

// Marks the column as the drop target, with a line before the card at `place` (or after the last card).
function showDropLine(column, place) {
  clearDropLine(column);
  column.classList.add("drop-target");
  const cards = column.querySelectorAll(".card");
  if (place < cards.length) cards[place].classList.add("drop-before");
  else if (cards.length > 0) cards[cards.length - 1].classList.add("drop-after");
}

// Removes the marks of showDropLine.
function clearDropLine(column) {
  column.classList.remove("drop-target");
  for (const c of column.querySelectorAll(".drop-before, .drop-after")) c.classList.remove("drop-before", "drop-after");
}
