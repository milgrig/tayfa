"""Remove the <style>...</style> block from index.html"""
import pathlib

p = pathlib.Path(r'C:\Cursor\TayfaWindows\kok\static\index.html')
text = p.read_text(encoding='utf-8')

# Find the style block to remove - it contains our marker
marker = '/* MARKER_START_REMOVE */'
if marker not in text:
    print('ERROR: Marker not found in file')
    exit(1)

# Find <style> tag that contains our marker
style_start = text.find('<style>')
if style_start == -1:
    print('ERROR: <style> tag not found')
    exit(1)

# Find closing </style>
style_end = text.find('</style>', style_start)
if style_end == -1:
    print('ERROR: </style> tag not found')
    exit(1)

# Include the </style> tag itself and the newline after it
style_end = style_end + len('</style>')
# Also remove leading whitespace before <style> on the same line
line_start = text.rfind('\n', 0, style_start)
if line_start != -1:
    style_start = line_start + 1  # Start from beginning of the line

# Also remove trailing newline after </style>
if style_end < len(text) and text[style_end] == '\n':
    style_end += 1

block_to_remove = text[style_start:style_end]
print(f'Removing {len(block_to_remove)} chars ({block_to_remove.count(chr(10))} lines)')
print(f'First 80 chars: {repr(block_to_remove[:80])}')
print(f'Last 80 chars: {repr(block_to_remove[-80:])}')

new_text = text[:style_start] + text[style_end:]
p.write_text(new_text, encoding='utf-8')

# Verify
new_text2 = p.read_text(encoding='utf-8')
print(f'Old size: {len(text)} chars')
print(f'New size: {len(new_text2)} chars')
print(f'Contains <style>: {"<style>" in new_text2}')
print(f'Contains link tags: {"themes.css" in new_text2}')
print('Done!')
