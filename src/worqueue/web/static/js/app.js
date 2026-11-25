// Wires the page together: switches between the views, loads them, and runs each write with its error shown
// and the page refreshed.

import { doneTask, editTask, getDone, getQueue, moveTask } from "./api.js";
import { setUpAddForm } from "./addform.js";
import { createBoard } from "./board.js";
import { createDetail } from "./detail.js";
import { ratioText, renderQueue } from "./queue.js";

const BOARD_HASH = "#kanban";
const errorBar = document.getElementById("error");
let view = "list";
let queue = { tasks: [], version: "none", taskVersions: {} };
let done = { tasks: [], total: 0, taskVersions: {} };

// Shows a message in the error bar, or hides the bar for null.
function showError(message) {
  errorBar.textContent = message ?? "";
  errorBar.hidden = message === null;
}

// Reads the queue again and draws the list, the count, and the ratio.
async function loadQueue() {
  const { tasks, version, task_versions } = await getQueue();
  queue = { tasks, version, taskVersions: task_versions };
  renderQueue(document.getElementById("queue"), tasks, {
    onOpen: openDetail,
    onMove: (id, before) => run(() => moveTask(id, queue.version, before)),
  });
  document.getElementById("queue-empty").hidden = tasks.length > 0;
  document.getElementById("count").textContent = `${tasks.length} 件`;
  document.getElementById("ratio").textContent = ratioText(tasks);
}

// Reads the done tasks again.
async function loadDone() {
  const { tasks, total, task_versions } = await getDone();
  done = { tasks, total, taskVersions: task_versions };
}

// Reads what the current view shows, and draws the board when it is shown.
async function loadView() {
  if (view !== "board") {
    await loadQueue();
    return;
  }
  await Promise.all([loadQueue(), loadDone()]);
  board.render({ tasks: queue.tasks, done: done.tasks, doneTotal: done.total });
}

// Reads the current view and the open task again.
async function refresh() {
  await Promise.all([loadView(), detail.reload()]);
}

// Runs a write; on success hides the error and refreshes, on failure shows it (and refreshes after a 409).
async function run(action) {
  try {
    await action();
    showError(null);
    await refresh();
  } catch (error) {
    showError(error.message);
    if (error.status === 409) await refresh().catch(() => {});
  }
}

// Opens a task in the detail panel.
function openDetail(id) {
  detail.open(id).catch((error) => showError(error.message));
}

// Returns the version of a task's file as the board read it ("none" if it was not read, which the server refuses).
function taskVersion(id) {
  return queue.taskVersions[id] ?? done.taskVersions[id] ?? "none";
}

// Runs the write of a drop on the board.
function writeDrop(id, action) {
  if (action.kind === "move") return run(() => moveTask(id, queue.version, action.before));
  if (action.kind === "done") return run(() => doneTask(id, taskVersion(id), ""));
  return run(() => editTask(id, { version: taskVersion(id), status: action.status }));
}

// Shows the view the URL's hash names (the board for #kanban, the list otherwise) and reads it.
function showView() {
  view = location.hash === BOARD_HASH ? "board" : "list";
  document.getElementById("list").hidden = view !== "list";
  document.getElementById("board").hidden = view !== "board";
  document.getElementById("view-list").setAttribute("aria-pressed", String(view === "list"));
  document.getElementById("view-board").setAttribute("aria-pressed", String(view === "board"));
  loadView().catch((error) => showError(error.message));
}

const detail = createDetail(run);
const board = createBoard(document.getElementById("board"), { onOpen: openDetail, onDrop: writeDrop });
setUpAddForm(run);
document.getElementById("view-list").addEventListener("click", () => {
  location.hash = "";
});
document.getElementById("view-board").addEventListener("click", () => {
  location.hash = BOARD_HASH;
});
window.addEventListener("hashchange", showView);
showView();
