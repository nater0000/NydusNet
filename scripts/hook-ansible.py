import pkgutil
import ansible
from PyInstaller.utils.hooks import collect_data_files

# --- Manual Submodule Collection ---
# We perform this manually because the 'excludes' parameter on PyInstaller's
# helper functions is not available in this version.

hiddenimports = []
exclude_prefix = 'ansible.template'  # This module has a Unix-only import

# Manually walk the ansible package to find all submodules
for importer, modname, ispkg in pkgutil.walk_packages(
    path=ansible.__path__,
    prefix=ansible.__name__ + '.',
    onerror=lambda x: None
):
    # Add the submodule to the list ONLY IF it's not the one we need to exclude
    if not modname.startswith(exclude_prefix):
        hiddenimports.append(modname)

# The error is from importing python modules, so collecting data files
# without an exclusion should be safe.
datas = collect_data_files('ansible')