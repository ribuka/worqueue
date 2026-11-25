// Sends the form that adds a task to the end of the queue.

import { addTask } from "./api.js";

// Wires the add form; `run(action)` runs the write and refreshes the page (given by app.js).
export function setUpAddForm(run) {
  const form = document.getElementById("add-form");
  const title = document.getElementById("add-title");
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    run(async () => {
      await addTask({
        title: title.value,
        kind: document.getElementById("add-kind").value,
        assignee: document.getElementById("add-assignee").value,
        due: document.getElementById("add-due").value || null,
      });
      title.value = "";
      document.getElementById("add-due").value = "";
    });
  });
}
