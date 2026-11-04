let currentPath = "";
let selectedFile = "";

function message(text, error=false) {
  const el = document.getElementById("status");
  el.textContent = text;
  el.style.color = error ? "#b42318" : "#28704b";
}
async function api(url, data) {
  const options = data ? {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(data)} : {};
  const response = await fetch(url, options);
  const result = await response.json();
  if (!response.ok || result.error) throw new Error(result.error || "Request failed.");
  return result;
}
function fullPath(name) { return currentPath ? currentPath + "/" + name : name; }
async function loadItems() {
  try {
    const data = await api("/api/list?path=" + encodeURIComponent(currentPath));
    document.getElementById("currentPath").textContent = "workspace" + (currentPath ? "/" + currentPath : "");
    document.getElementById("items").innerHTML = data.items.map(item => `
      <div class="item">
        <div class="name">${item.type === "folder" ? "📁" : "📄"} ${escapeHtml(item.name)}</div>
        <small>${item.type === "folder" ? "Folder" : item.size + " bytes"}</small>
        <div class="item-actions">
          ${item.type === "folder" ? `<button onclick="openFolder('${encodeURIComponent(item.name)}')">Open</button>` : `<button onclick="openFile('${encodeURIComponent(item.name)}')">Read/Edit</button>`}
          <button onclick="renameItem('${encodeURIComponent(item.name)}')">Rename</button>
          <button onclick="copyMove('${encodeURIComponent(item.name)}','copy')">Copy</button>
          <button onclick="copyMove('${encodeURIComponent(item.name)}','move')">Move</button>
          <button onclick="deleteItem('${encodeURIComponent(item.name)}')">Delete</button>
        </div>
      </div>`).join("") || "<p>No files yet. Create your first file or folder.</p>";
    document.getElementById("tree").innerHTML = renderTree(data.tree, "");
    message("Workspace loaded.");
  } catch(e) { message(e.message, true); }
}
function renderTree(node, path) {
  const current = path ? path + "/" + node.name : (node.name === "workspace" ? "" : node.name);
  let html = `<div>📁 ${node.name === "workspace" ? "workspace" : `<button onclick="navigate('${encodeURIComponent(current)}')">${escapeHtml(node.name)}</button>`}</div>`;
  for (const child of node.children || []) {
    if (child.type === "folder") html += `<div style="padding-left:14px">${renderTree(child, current)}</div>`;
    else html += `<div style="padding-left:28px">📄 ${escapeHtml(child.name)}</div>`;
  }
  return html;
}
function escapeHtml(value) { return value.replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c])); }
async function createItem(action) {
  const name = prompt(action === "create_file" ? "Enter file name (example: notes.txt)" : "Enter folder name");
  if (!name) return;
  try { const r = await api("/api/action", {action, path:currentPath, name}); message(r.message); loadItems(); }
  catch(e) { message(e.message, true); }
}
async function openFolder(encoded) { currentPath = fullPath(decodeURIComponent(encoded)); selectedFile=""; document.getElementById("editor").value=""; document.getElementById("editorName").textContent="No file selected"; loadItems(); }
function navigate(encoded) { currentPath = decodeURIComponent(encoded); loadItems(); }
function goUp() { currentPath = currentPath.includes("/") ? currentPath.substring(0,currentPath.lastIndexOf("/")) : ""; loadItems(); }
async function openFile(encoded) {
  const rel = fullPath(decodeURIComponent(encoded));
  try {
    const r = await api("/api/read?path=" + encodeURIComponent(rel));
    selectedFile = rel; document.getElementById("editor").value = r.content;
    document.getElementById("editorName").textContent = rel; message("File opened.");
  } catch(e) { message(e.message, true); }
}
async function saveFile() {
  if (!selectedFile) return message("Select a file first.", true);
  try { const r = await api("/api/action", {action:"write", file:selectedFile, content:document.getElementById("editor").value}); message(r.message); }
  catch(e) { message(e.message, true); }
}
async function renameItem(encoded) {
  const oldName = decodeURIComponent(encoded), name = prompt("Enter new name", oldName);
  if (!name || name === oldName) return;
  try { const r = await api("/api/action", {action:"rename", item:fullPath(oldName), name}); message(r.message); loadItems(); }
  catch(e) { message(e.message, true); }
}
async function copyMove(encoded, action) {
  const name = decodeURIComponent(encoded);
  const destination = prompt("Destination folder path relative to workspace (leave blank for workspace root)", "");
  if (destination === null) return;
  try { const r = await api("/api/action", {action, item:fullPath(name), destination}); message(r.message); loadItems(); }
  catch(e) { message(e.message, true); }
}
async function deleteItem(encoded) {
  const name = decodeURIComponent(encoded);
  if (!confirm(`Delete "${name}"? This cannot be undone.`)) return;
  try { const r = await api("/api/action", {action:"delete", item:fullPath(name)}); message(r.message); loadItems(); }
  catch(e) { message(e.message, true); }
}
async function searchItems() {
  const name = document.getElementById("searchInput").value.trim();
  if (!name) return message("Enter a search term.", true);
  try {
    const r = await api("/api/action", {action:"search", name});
    document.getElementById("items").innerHTML = r.matches.map(x => `<div class="item"><div class="name">🔎 ${escapeHtml(x)}</div></div>`).join("") || "<p>No matches found.</p>";
    message(`${r.matches.length} result(s) found.`);
  } catch(e) { message(e.message, true); }
}
async function sortItems() {
  try {
    const r = await api("/api/action", {action:"sort", path:currentPath});
    message("Sorted A–Z: " + r.items.join(", "));
    loadItems();
  } catch(e) { message(e.message, true); }
}
loadItems();
