def parse_policy_markdown(markdown_text: str) -> list[dict]:
    chunks = []
    lines = markdown_text.splitlines()
    
    current_h2 = ""
    current_h3 = ""
    buffer = []
    
    def flush_chunk():
        nonlocal current_h2, current_h3, buffer
        content = "\n".join(buffer).strip()
        if (current_h2 or current_h3) and content:
            if current_h3:
                citation = f"policy_mock_vi.md > {current_h3}"
                rendered_text = f"## {current_h2}\n### {current_h3}\n{content}"
            else:
                citation = f"policy_mock_vi.md > {current_h2}"
                rendered_text = f"## {current_h2}\n{content}"
                
            chunks.append({
                "section_h2": current_h2,
                "section_h3": current_h3,
                "citation": citation,
                "rendered_text": rendered_text
            })
        buffer = []

    for line in lines:
        if line.startswith("## "):
            flush_chunk()
            current_h2 = line[3:].strip()
            current_h3 = ""
        elif line.startswith("### "):
            flush_chunk()
            current_h3 = line[4:].strip()
        elif line.startswith("# "):
            flush_chunk()
            current_h2 = ""
            current_h3 = ""
        else:
            buffer.append(line)
            
    flush_chunk()
    return chunks


