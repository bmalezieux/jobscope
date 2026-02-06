import datetime

project = "JobScope"
author = "Benoît Malézieux"
release = "0.1.0"

extensions = []

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

html_theme = "alabaster"
html_static_path = ["_static"]

# Keep the build reproducible across machines.
html_last_updated_fmt = "%Y-%m-%d"

today = datetime.date.today().isoformat()
