import PyInstaller.__main__
import os
import requests
import zipfile
import io
import logging
import toml
import shutil
import tempfile

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_config_value(key: str) -> str:
    """Reads a value from the project's pyproject.toml file."""
    try:
        with open('pyproject.toml', 'r') as f:
            data = toml.load(f)
            return data['tool']['nydusnet'][key]
    except (FileNotFoundError, KeyError) as e:
        logging.error(f"Failed to read '{key}' from pyproject.toml: {e}")
        return None


def download_syncthing(version: str):
    """Downloads and extracts the full Syncthing package if it doesn't already exist."""
    if not version:
        logging.error("No Syncthing version provided. Aborting download.")
        return False

    url = f"https://github.com/syncthing/syncthing/releases/download/{version}/syncthing-windows-amd64-{version}.zip"
    syncthing_dir = os.path.join('resources', 'syncthing')
    syncthing_exe_path = os.path.join(syncthing_dir, 'syncthing.exe')

    if os.path.exists(syncthing_exe_path):
        logging.info("Syncthing executable already exists. Skipping download.")
        return True

    logging.info(f"Syncthing not found. Downloading and extracting from {url}...")
    os.makedirs(syncthing_dir, exist_ok=True)

    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()

        with tempfile.TemporaryDirectory() as temp_dir:
            with zipfile.ZipFile(io.BytesIO(response.content)) as zip_ref:
                zip_ref.extractall(temp_dir)

            # The zip extracts to a subfolder, e.g., 'syncthing-windows-amd64-v1.27.7'
            # We need to find that subfolder and move its contents.
            extracted_folder_name = zip_ref.infolist()[0].filename.split('/')[0]
            source_folder = os.path.join(temp_dir, extracted_folder_name)

            # Copy all files from the extracted folder to our target directory
            for item in os.listdir(source_folder):
                s = os.path.join(source_folder, item)
                d = os.path.join(syncthing_dir, item)
                if os.path.isfile(s):
                    shutil.copy2(s, d)

        if os.path.exists(syncthing_exe_path):
            logging.info("Syncthing package downloaded and extracted successfully.")
            return True
        else:
            logging.error("Extraction failed: syncthing.exe not found after process.")
            return False

    except (requests.exceptions.RequestException, zipfile.BadZipFile, IndexError) as e:
        logging.error(f"Failed during Syncthing download/extraction: {e}")
        return False

if __name__ == '__main__':
    syncthing_version = get_config_value('syncthing_version')
    if not syncthing_version:
        logging.error("Build aborted: Syncthing version not found in pyproject.toml.")
    elif not download_syncthing(syncthing_version):
        logging.error("Build process aborted because Syncthing could not be downloaded.")
    else:
        pyinstaller_args = [
            'src/main.py',
            '--name', 'NydusNet',
            '--onefile',
            '--windowed',
            '--noconfirm',
            '--clean',
            '--add-data', f'resources/syncthing{os.pathsep}syncthing'
        ]
            
        logging.info(f"Running PyInstaller with args: {' '.join(pyinstaller_args)}")
        PyInstaller.__main__.run(pyinstaller_args)
        logging.info("PyInstaller build complete.")