"""Record this isolated interpreter's distributions, licenses and reproducibility hashes."""
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys

def main():
    import psutil
    import torch
    root=Path(__file__).resolve().parent; target=root/'neural_environment'; target.mkdir(exist_ok=True)
    licenses=target/'licenses'; licenses.mkdir(exist_ok=True)
    packages=[]
    for dist in sorted(metadata.distributions(),key=lambda d:d.metadata['Name'].lower()):
        name=dist.metadata['Name']; files=[]
        for f in dist.files or []:
            if any(part.lower().startswith(('license','copying','notice')) for part in Path(str(f)).parts):
                source=Path(dist.locate_file(f))
                if source.is_file():
                    dest=licenses/name/str(f); dest.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(source,dest)
                    files.append(str(dest.relative_to(target)))
        packages.append({'name':name,'version':dist.version,'license_expression':dist.metadata.get('License-Expression'),
                         'license_metadata':dist.metadata.get('License'),'license_files':files})
    freeze=subprocess.check_output([sys.executable,'-m','pip','freeze','--all'],text=True)
    (target/'requirements-lock.txt').write_text(freeze,encoding='utf-8')
    source_license=Path(sys.base_prefix)/'LICENSE.txt'
    if source_license.is_file():shutil.copyfile(source_license,licenses/'Python-LICENSE.txt')
    report={'python':sys.version,'executable':sys.executable,'base_prefix':sys.base_prefix,'platform':platform.platform(),
            'processor':platform.processor(),'logical_cpus':psutil.cpu_count(),'physical_cpus':psutil.cpu_count(logical=False),
            'system_ram_bytes':psutil.virtual_memory().total,'torch':torch.__version__,'cuda_available':torch.cuda.is_available(),
            'packages':packages}
    (target/'environment.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    hashes={}
    for folder in (root/'neural_environment',root/'neural_artifacts'/'3c5b1-seed1729'):
        for file in sorted(folder.rglob('*')):
            if file.is_file() and '.hub-cache' not in file.parts and file.name!='artifact-hashes.json':
                hashes[str(file.relative_to(root))]=hashlib.sha256(file.read_bytes()).hexdigest()
    for file in sorted(root.glob('*neural*.py')):hashes[file.name]=hashlib.sha256(file.read_bytes()).hexdigest()
    (target/'artifact-hashes.json').write_text(json.dumps(hashes,indent=2),encoding='utf-8')
    print(json.dumps({'packages':len(packages),'files_hashed':len(hashes),'torch':torch.__version__,'cuda':torch.cuda.is_available()}))

if __name__=='__main__':main()
