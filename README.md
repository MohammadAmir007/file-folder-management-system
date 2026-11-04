# File & Folder Management System

An academic project demonstrating file and folder operations with a Python backend, HTML/CSS/JavaScript interface, basic DSA concepts, and a C file-handling example.

## Features
- Create files and folders
- Read and write text files
- Rename, copy, move and delete items
- Search for files and folders by name
- View folder hierarchy and sort items alphabetically
- C file I/O demonstration in `file_demo.c`

## Technologies
- Python 3 (standard library: `http.server`, `pathlib`, `os`, `shutil`)
- HTML, CSS and JavaScript
- DSA concepts: folder tree, searching and sorting
- C: `fopen`, `fprintf`, `fgets`, `fclose`

## Run the project
1. Install Python 3.
2. Open a terminal in this project folder.
3. Run:

   ```bash
   python app.py
   ```

4. Open http://localhost:8000 in your browser.
5. The app manages files only inside the `workspace` folder.

## Run the C demonstration
Compile with GCC:

```bash
gcc file_demo.c -o file_demo
./file_demo
```

On Windows, run `file_demo.exe` after compiling.

## Project structure

```text
file-folder-management-system/
├── app.py
├── file_demo.c
├── README.md
├── static/
│   ├── index.html
│   ├── style.css
│   └── script.js
└── workspace/
```

## Safety note
This is a local academic demonstration. Delete operations are permanent within the workspace. Do not expose the development server to the public internet.
