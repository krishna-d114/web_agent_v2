from contextlib import asynccontextmanager
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import re
import yaml

SERVER_PARAMS = StdioServerParameters(
    command="npx",
    args=["@playwright/mcp@latest"],
)

EXCLUDED_TOOLS = {"browser_run_code_unsafe"}


import re
import yaml

class DOMCompressor:
    """Compress Playwright MCP YAML accessibility tree snapshots."""
    
    def __init__(self, max_tokens=5000):
        self.max_tokens = max_tokens
        self.ref_counter = 0
        
    def compress(self, raw_text: str) -> str:
        # Extract YAML snapshot block from the MCP response
        yaml_block = self._extract_yaml(raw_text)
        if not yaml_block:
            return raw_text  # Fallback: return raw if we can't parse
        
        try:
            tree = yaml.safe_load(yaml_block)
        except yaml.YAMLError:
            return raw_text
        
        lines = []
        self._walk_tree(tree, lines, depth=0)
        
        return self._finalize(lines, raw_text)
    
    def _extract_yaml(self, text: str) -> str:
        """Extract the YAML snapshot between ```yaml and ```."""
        match = re.search(r'```yaml\n(.*?)\n```', text, re.DOTALL)
        if match:
            return match.group(1)
        # Also try without code fences
        if 'Snapshot' in text and '[ref=' in text:
            # Find the YAML-like part
            lines = text.split('\n')
            yaml_lines = []
            in_yaml = False
            for line in lines:
                if line.strip().startswith('- ') or line.strip().startswith('  '):
                    yaml_lines.append(line)
                    in_yaml = True
                elif in_yaml and line.strip():
                    break
            return '\n'.join(yaml_lines)
        return ""
    
    def _walk_tree(self, node, lines, depth=0):
        """Recursively walk the YAML tree and extract interactive elements + structure."""
        if isinstance(node, list):
            for item in node:
                self._walk_tree(item, lines, depth)
        elif isinstance(node, dict):
            for key, value in node.items():
                # key is like "generic [ref=e2]" or "button \"Search\" [ref=e34]"
                ref = self._extract_ref(key)
                tag = self._extract_tag(key)
                text = self._extract_text(key)
                
                # Skip purely structural containers at deep levels
                if tag in ('generic', 'banner', 'navigation', 'main', 'contentinfo', 'complementary'):
                    if depth > 2 and not ref:
                        # Deep structural noise, skip unless it has children
                        if isinstance(value, (list, dict)) and value:
                            self._walk_tree(value, lines, depth + 1)
                        continue
                
                # Interactive elements — ALWAYS keep with ref
                if tag in ('button', 'link', 'textbox', 'combobox', 'searchbox', 
                           'checkbox', 'radio', 'menuitem', 'tab', 'menuitemcheckbox',
                           'menuitemradio', 'option', 'listbox', 'slider', 'spinbutton',
                           'switch', 'treeitem', 'gridcell', 'cell', 'heading'):
                    
                    label = text or self._extract_label_from_children(value)
                    ref_id = ref or f"e{self.ref_counter}"
                    if not ref:
                        self.ref_counter += 1
                    
                    if tag == 'link':
                        href = self._extract_href(value)
                        lines.append(f"[{ref_id}] LINK: {label} (href: {href})")
                    elif tag in ('textbox', 'searchbox', 'combobox'):
                        lines.append(f"[{ref_id}] INPUT ({tag}): {label}")
                    elif tag == 'button':
                        lines.append(f"[{ref_id}] BUTTON: {label}")
                    elif tag in ('heading',):
                        level = self._extract_heading_level(key)
                        lines.append(f"{'#' * level} {label}")
                    else:
                        lines.append(f"[{ref_id}] {tag.upper()}: {label}")
                
                # Content elements — keep if near top or have text
                elif tag in ('paragraph', 'text', 'StaticText', 'label', 'img', 'image'):
                    if text and len(text) > 3:
                        lines.append(text[:120])
                
                # Recurse into children
                if isinstance(value, (list, dict)):
                    self._walk_tree(value, lines, depth + 1)
                    
        elif isinstance(node, str):
            if len(node.strip()) > 3 and len(node.strip()) < 200:
                lines.append(node.strip())
    
    def _extract_ref(self, key: str) -> str:
        match = re.search(r'\[ref=([^\]]+)\]', key)
        return match.group(1) if match else ""
    
    def _extract_tag(self, key: str) -> str:
        # "button \"Search\" [ref=e34]" -> "button"
        # "generic [ref=e2]" -> "generic"
        # "link \"Home\" [ref=e5]" -> "link"
        match = re.match(r'^([a-zA-Z]+)', key.strip())
        return match.group(1).lower() if match else "unknown"
    
    def _extract_text(self, key: str) -> str:
        # Extract quoted text: "button \"Search\"" -> "Search"
        match = re.search(r'"([^"]+)"', key)
        return match.group(1) if match else ""
    
    def _extract_label_from_children(self, value) -> str:
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    for k in item.keys():
                        text = self._extract_text(k)
                        if text:
                            return text
                elif isinstance(item, str):
                    if item.strip():
                        return item.strip()[:60]
        return ""
    
    def _extract_href(self, value) -> str:
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    for k, v in item.items():
                        if 'url' in k.lower() or 'href' in k.lower():
                            if isinstance(v, str):
                                return v
        return ""
    
    def _extract_heading_level(self, key: str) -> int:
        # Try to extract level from value or key
        match = re.search(r'level\s*(\d)', key, re.I)
        if match:
            return int(match.group(1))
        return 2  # Default
    
    def _finalize(self, lines: list, raw_text: str) -> str:
        # Deduplicate while preserving order
        seen = set()
        result = []
        for line in lines:
            line = line.strip()
            if not line or line in seen:
                continue
            seen.add(line)
            result.append(line)
        
        # Truncate to token budget
        max_chars = self.max_tokens * 4
        out = '\n'.join(result)
        
        if len(out) > max_chars:
            # Keep all interactive elements (lines with [ref= or [e)
            interactive = [l for l in result if re.search(r'\[ref=|\[e\d+\]', l)]
            content = [l for l in result if not re.search(r'\[ref=|\[e\d+\]', l)]
            
            out = '\n'.join(interactive)
            remaining = max_chars - len(out) - 100
            for line in content:
                if len(out) + len(line) < remaining:
                    out += '\n' + line
                else:
                    break
            out += '\n... [truncated]'
        
        # Add header showing compression
        raw_tokens = len(raw_text) // 4
        compressed_tokens = len(out) // 4
        return (
            f"--- PAGE SNAPSHOT ({raw_tokens}→{compressed_tokens} est.tokens) ---\n"
            f"{out}\n"
            f"--- Use exact refs like [e34] for clicks/typing ---"
        )

@asynccontextmanager
async def mcp_session():
    async with stdio_client(SERVER_PARAMS) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


def mcp_tool_to_openai_schema(tool) -> dict:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description or "",
            "parameters": tool.inputSchema,
        },
    }


async def get_openai_tools(session: ClientSession) -> list[dict]:
    result = await session.list_tools()
    tools = [
        mcp_tool_to_openai_schema(t)
        for t in result.tools
        if t.name not in EXCLUDED_TOOLS
    ]

    tools.append({
        "type": "function",
        "function": {
            "name": "read_skill_file",
            "description": "Read the full content of a previously saved skill file, given its path from the memory index (e.g. 'youtube/play_video.md').",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                },
                "required": ["path"],
            },
        },
    })

    tools.append({
        "type": "function",
        "function": {
            "name": "mark_task_complete",
            "description": "Call this when the task has been fully completed, or when you determine it cannot be completed. If successful, can optionally include a new skill to save to memory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "success": {"type": "boolean"},
                    "reason": {"type": "string"},
                    "skill_site": {
                        "type": "string",
                        "description": "Lowercase site name, e.g. 'youtube', 'amazon'. Omit if nothing worth saving.",
                    },
                    "skill_name": {
                        "type": "string",
                        "description": "Short filename-safe skill name, e.g. 'play_video'.",
                    },
                    "skill_type": {
                        "type": "string",
                        "enum": ["static_link", "url_pattern", "no_cache"],
                        "description": "static_link = one fixed reusable URL. url_pattern = templated URL with a substitutable term. no_cache = target changes over time, don't cache a link, just record the workflow.",
                    },
                    "skill_content": {
                        "type": "string",
                        "description": "Full markdown body for the skill file: what the task is, the Type, the link/pattern (if any), and notes on when/how to reuse it.",
                    },
                },
                "required": ["success", "reason"],
            },
        },
    })

    return tools


async def call_mcp_tool(session: ClientSession, name: str, arguments: dict) -> str:
    result = await session.call_tool(name, arguments=arguments)
    parts = [block.text for block in result.content if hasattr(block, "text")]
    raw_text = "\n".join(parts) if parts else "(no text content returned)"

    if name in ("browser_snapshot", "browser_find") and len(raw_text) > 1500:
        compressor = DOMCompressor(max_tokens=5000)
        compressed = compressor.compress(raw_text)
        return (
            f"--- PAGE SNAPSHOT ({len(raw_text) // 4}→{len(compressed) // 4} est.tokens) ---\n"
            f"{compressed}\n"
            f"--- Use exact refs like [e12] for clicks/typing ---"
        )

    return raw_text