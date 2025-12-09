#!/usr/bin/env python3
"""
Liliw Tourism - Template Animation Updater
This script helps update all templates to include the new animation system
"""

import os
import re

TEMPLATE_DIR = "templates"
HEAD_INCLUDE = "{% include 'head-includes.html' %}"
SCRIPT_INCLUDE = "{% include 'scripts-includes.html' %}"

# Patterns to match old CSS includes
OLD_CSS_PATTERNS = [
    r'<link rel="stylesheet" href="\{\{ url_for\(\'static\', filename=\'styles/main\.css\'\) \}\}">',
    r'<link rel="stylesheet" href="\{\{ url_for\(\'static\', filename=\'styles/theme-override\.css\'\) \}\}">',
]

# Animation classes to add to common elements
ANIMATION_MAP = {
    'hero-section': 'gradient-animate',
    'hero-content': 'fade-in-up',
    'section-header': 'reveal',
    'card': 'hover-lift zoom-container',
    'btn': 'hover-scale',
    'cta-btn': 'hover-glow'
}

def update_template(filepath):
    """Update a single template file with animation includes"""
    print(f"Processing: {filepath}")

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Check if already updated
    if HEAD_INCLUDE in content:
        print(f"  ✓ Already updated")
        return

    # Add head includes after <title>
    if '<title>' in content and HEAD_INCLUDE not in content:
        content = re.sub(
            r'</title>\s*\n',
            f'</title>\n    {HEAD_INCLUDE}\n',
            content,
            count=1
        )
        print(f"  + Added head includes")

    # Add script includes before </body>
    if '</body>' in content and SCRIPT_INCLUDE not in content:
        content = re.sub(
            r'</body>',
            f'    {SCRIPT_INCLUDE}\n</body>',
            content,
            count=1
        )
        print(f"  + Added script includes")

    # Write back
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"  ✓ Updated successfully\n")

def main():
    """Main function to update all templates"""
    print("=" * 60)
    print("Liliw Tourism - Animation System Update")
    print("=" * 60)
    print()

    # Find all HTML templates
    templates = []
    for root, dirs, files in os.walk(TEMPLATE_DIR):
        for file in files:
            if file.endswith('.html') and file not in ['header.html', 'footer.html', 'head-includes.html', 'scripts-includes.html']:
                templates.append(os.path.join(root, file))

    print(f"Found {len(templates)} templates to update\n")

    # Update each template
    for template in templates:
        try:
            update_template(template)
        except Exception as e:
            print(f"  ✗ Error: {e}\n")

    print("=" * 60)
    print("Update complete!")
    print("=" * 60)
    print()
    print("Next steps:")
    print("1. Review updated templates")
    print("2. Add animation classes to specific elements")
    print("3. Test all pages")
    print("4. Refer to ANIMATION_GUIDE.md for usage")

if __name__ == '__main__':
    main()
