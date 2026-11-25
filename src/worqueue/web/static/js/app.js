// Wires the page together: loads the queue, and runs each write with its error shown and the page refreshed.

import { getQueue, moveTask } from "./api.js";
import { setUpAddForm } from "./addform.js";
import { createDetail } from "./detail.js";
import { ratioText, renderQueue } from "./queue.js";

const errorBar = document.getElementById("error");
let queueVersion = "none";

// Shows a message in the error bar, or hides the bar for null.
function showError(message) {
  errorBar.textContent = message ?? "";
  errorBar.hidden = message === null;
}

// Reads the queue again and draws it.
async function loadQueue() {
  const { tasks, version } = await getQueue();
  queueVersion = version;
  renderQueue(document.getElementById("queue"), tasks, {
    onOpen: (id) => detail.open(id).catch((error) => showError(error.message)),
    onMove: (id, before) => run(() => moveTask(id, queueVersion, before)),
  });
  document.getElementById("queue-empty").hidden = tasks.length > 0;
  document.getElementById("count").textContent = `${tasks.length} 件`;
  document.getElementById("ratio").textContent = ratioText(tasks);
}

// Reads the queue and the open task again.
async function refresh() {
  await Promise.all([loadQueue(), detail.reload()]);
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

const detail = createDetail(run);
setUpAddForm(run);
loadQueue().catch((error) => showError(error.message));
