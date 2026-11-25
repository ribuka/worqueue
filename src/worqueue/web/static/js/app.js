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
  // The rows and the version they are moved with come from the same read.
  renderQueue(document.getElementById("queue"), tasks, {
    onOpen: openDetail,
    onMove: (id, before) => run(() => moveTask(id, version, before)),
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
  board.render({
    tasks: queue.tasks,
    done: done.tasks,
    doneTotal: done.total,
    queueVersion: queue.version,
    taskVersions: { ...done.taskVersions, ...queue.taskVersions },
  });
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

// Runs the write of a drop on the board, with the versions of the board as drawn (`drawn`): never those of a
// later read, which could match a file changed after the cards were drawn. A task without a version is sent
// as "none", which the server refuses.
function writeDrop(id, action, drawn) {
  if (action.kind === "move") return run(() => moveTask(id, drawn.queueVersion, action.before));
  const version = drawn.taskVersions[id] ?? "none";
  if (action.kind === "done") return run(() => doneTask(id, version, ""));
  return run(() => editTask(id, { version, status: action.status }));
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
