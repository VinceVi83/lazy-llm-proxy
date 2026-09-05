import os
import glob

from config.conf_manager import cfg

REPLACEMENTS = {
    'PROJECT_PATH': str(cfg.project_dir),
    'LOG_PATH': str(cfg.config_dir / 'debug.log'),
    'PYTHON_PATH': str(cfg.conf.python_path),
    'USER': os.getlogin(),
}

EXTENSIONS = ['.sh', '.service', '.py']

for path in glob.glob('*'):
    if not os.path.isfile(path) or os.path.splitext(path)[1] not in EXTENSIONS:
        continue
    with open(path, 'r') as file:
        original = file.read()
    content = original
    cpt = 0
    for old, new in REPLACEMENTS.items():
        cpt += 1
        replacement = '#' + old + '#'
        content = content.replace(replacement, new)
    if content != original:
        with open(path, 'w') as file:
            file.write(content)
        print(f'Modifié: {path} ({cpt} remplacements)')

