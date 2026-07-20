import re
from pathlib import Path

LONG_TERM_PATH = Path("memory/long_term.txt")
SHORT_TERM_DIR = Path("memory/short_term")

STOPWORDS = {
    "a", "an", "the", "on", "in", "at", "to", "of", "and", "or", "is",
    "check", "open", "go", "play", "for", "with", "its", "it", "this",
    "that", "please", "only", "if", "you", "your", "just", "latest",
}

def _ensure_dirs():
    LONG_TERM_PATH.parent.mkdir(parents = True,exist_ok =True)
    LONG_TERM_PATH.touch(exist_ok=True)
    SHORT_TERM_DIR.mkdir(parents=True, exist_ok=True)


def get_memory_index(task:str)->str:
    _ensure_dirs()
    task_words = set(re.findall(r"[a-zA-Z0-9]+",task.lower()))-STOPWORDS
    if not task_words:
        return "(no relevant past experience found)"
    
    matches = []
    for line in LONG_TERM_PATH.read_text(encoding = "utf-8").splitlines():
        if not line.strip():
            continue
        
        task_field = re.search(r'task = "([^"]*)"',line)
        if not task_field:
            continue

        line_words = set(re.findall(r"{a-zA-Z0-9]+",task_field.group(1).lower()))
        if task_words & line_words:
            matches.append(line)
    
    if not matches:
        return "(no relevant past experience found)"
    return "\n".join(dict.fromkeys(matches))

def read_skill_file(path:str)->str:
    full_path = SHORT_TERM_DIR/path
    
    try:
        full_path.resolve().relative_to(SHORT_TERM_DIR.resolve())
    except ValueError:
        return f"Error: '{path}' is not a valid skill file path."
    
    if not full_path.exists():
        return full_path.read_text(encoding = "utf-8")
    

def save_skill(task:str,site:str,skill_name:str,skill_type:str,content:str)->str:
    _ensure_dirs()
    safe_skill_name = re.sub(r"[^a-zA-Z0-9_\-]","_",skill_name)
    if not safe_skill_name.endswith(".md"):
        safe_skill_name +=".md"
    
    site_dir = SHORT_TERM_DIR / site
    site_dir.mkdir(parents = True,exist_ok = True)
    
    skill_path = site_dir/safe_skill_name
    skill_path.write_text(content,encoding = "utf-8")

    relative_path = f"{site}/{safe_skill_name}"
    index_line = (
        f'task="{task} | site = {site} | skill = {relative_path}"'
        f'|type = {skill_type}'
    )
    with open(LONG_TERM_PATH,"a",encoding = "utf-8") as f:
        f.write(index_line +"\n")
    
    return relative_path
