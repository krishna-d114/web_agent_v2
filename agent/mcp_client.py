from contextlib import asynccontextmanager
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import re

SERVER_PARAMS = StdioServerParameters(
    command="npx",
    args=["@playwright/mcp@latest"],
)

EXCLUDED_TOOLS = {"browser_run_code_unsafe"}


class DOMCompressor:
    """Fast regex-based DOM downsampling. No external deps."""

    INTERACTIVE = {'a', 'button', 'input', 'select', 'textarea', 'option',
                   'details', 'dialog', 'form', 'label'}
    CONTENT = {'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote', 'pre',
               'code', 'table', 'tr', 'td', 'th', 'ul', 'ol', 'li', 'strong', 'b', 'em', 'i'}
    NOISE = {'script', 'style', 'noscript', 'meta', 'link', 'template', 'head', 'base',
             'source', 'track', 'param', 'area', 'svg', 'canvas', 'video', 'audio', 'iframe'}

    KEEP_ATTRS = {'href', 'src', 'alt', 'title', 'type', 'name', 'value', 'placeholder',
                  'aria-label', 'role', 'for', 'action', 'method', 'id', 'class'}

    def __init__(self, max_tokens=6000):
        self.max_tokens = max_tokens
        self.ref_counter = 0

    def compress(self, html: str) -> str:
        self.ref_counter = 0
        html = self._strip_noise(html)
        lines = self._extract_interactive(html)
        lines += self._extract_content(html)
        return self._finalize(lines)

    def _strip_noise(self, html: str) -> str:
        html = re.sub(r'<head[^>]*>.*?</head>', '', html, flags=re.DOTALL | re.I)
        for tag in self.NOISE:
            html = re.sub(rf'<{tag}\b[^>]*>.*?</{tag}>', '', html, flags=re.DOTALL | re.I)
            html = re.sub(rf'<{tag}\b[^/]*/?\s*>', '', html, flags=re.I)
        return html

    def _extract_interactive(self, html: str) -> list:
        lines = []
        for tag in self.INTERACTIVE:
            pattern = rf'<{tag}\b([^>]*)>(.*?)</{tag}>'
            for match in re.finditer(pattern, html, re.DOTALL | re.I):
                attrs_str, content = match.group(1), match.group(2)
                attrs = self._parse_attrs(attrs_str)
                ref = f"e{self.ref_counter}"
                self.ref_counter += 1

                text = re.sub(r'<[^>]+>', '', content).strip()[:60]
                label = text or attrs.get('aria-label', '') or attrs.get('placeholder', '') or attrs.get('value', '') or tag

                if tag == 'a':
                    lines.append(f"[{ref}] LINK: {label} (href: {attrs.get('href', '')})")
                elif tag == 'button':
                    lines.append(f"[{ref}] BUTTON: {label}")
                elif tag == 'input':
                    lines.append(f"[{ref}] INPUT ({attrs.get('type', 'text')}): placeholder={attrs.get('placeholder', '')} value={attrs.get('value', '')}")
                elif tag == 'select':
                    lines.append(f"[{ref}] SELECT: {label}")
                elif tag == 'textarea':
                    lines.append(f"[{ref}] TEXTAREA: {label}")
                elif tag == 'form':
                    lines.append(f"[{ref}] FORM: action={attrs.get('action', '')}")
                else:
                    lines.append(f"[{ref}] {tag.upper()}: {label}")
        return lines

    def _extract_content(self, html: str) -> list:
        lines = []
        for i in range(1, 7):
            pattern = rf'<h{i}\b[^>]*>(.*?)</h{i}>'
            for m in re.finditer(pattern, html, re.DOTALL | re.I):
                text = re.sub(r'<[^>]+>', '', m.group(1)).strip()
                if text:
                    lines.append(f"{'#' * i} {text}")
        paras = re.findall(r'<p\b[^>]*>(.*?)</p>', html, re.DOTALL | re.I)
        for p in paras[:5]:
            text = re.sub(r'<[^>]+>', '', p).strip()
            if len(text) > 20:
                lines.append(text[:200] + ('...' if len(text) > 200 else ''))
        return lines

    def _parse_attrs(self, s: str) -> dict:
        return {m.group(1).lower(): m.group(2)
                for m in re.finditer(r'([a-zA-Z0-9\-:]+)\s*=\s*["\']([^"\']*)["\']', s)}

    def _finalize(self, lines: list) -> str:
        seen = set()
        result = []
        for line in lines:
            if line not in seen and line.strip():
                result.append(line)
                seen.add(line)
        max_chars = self.max_tokens * 4
        out = '\n'.join(result)
        if len(out) > max_chars:
            interactive = [l for l in result if l.startswith('[e')]
            content = [l for l in result if not l.startswith('[e')]
            out = '\n'.join(interactive)
            remaining = max_chars - len(out) - 100
            for line in content:
                if len(out) + len(line) < remaining:
                    out += '\n' + line
                else:
                    break
            out += '\n... [truncated]'
        return out


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