// Calls the server's API and turns its error responses into ApiError.

// An error response: the HTTP status and the message to show.
export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

// Sends one request with an optional JSON body; returns the parsed JSON, or throws ApiError.
async function request(method, path, body) {
  const options = { method, headers: {} };
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  const response = await fetch(path, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = response.status === 422 ? "入力が正しくありません" : data.error ?? `エラー（${response.status}）`;
    throw new ApiError(response.status, message);
  }
  return data;
}

// Returns {tasks, version}: the queue from the top and the version of queue.md.
export const getQueue = () => request("GET", "/api/queue");

// Returns {task, body, version}: one task with its Markdown, its body, and its file's version.
export const getTask = (id) => request("GET", `/api/tasks/${id}`);

// Creates a task at the end of the queue; returns {task}.
export const addTask = (fields) => request("POST", "/api/tasks", fields);

// Changes the given fields of a task; returns {task, changed}.
export const editTask = (id, fields) => request("PATCH", `/api/tasks/${id}`, fields);

// Adds one history entry; returns {task}.
export const logTask = (id, version, content) => request("POST", `/api/tasks/${id}/log`, { version, content });

// Marks a task done, with the reason if any; returns {task}.
export const doneTask = (id, version, reason) =>
  request("POST", `/api/tasks/${id}/done`, reason ? { version, reason } : { version });

// Moves a task before another (an ID) or to the bottom (null); returns {task, from}.
export const moveTask = (id, version, before) => request("POST", `/api/tasks/${id}/move`, { version, before });
