import PyInstaller.__main__
import os
import requests
import zipfile
import io
import logging
import toml
import subprocess

# Configure basic logging to see the download progress
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
    """
    Downloads the Syncthing executable for Windows if it doesn't already exist.
    """
    if not version:
        logging.error("No Syncthing version provided. Aborting download.")
        return False

    url = f"https://github.com/syncthing/syncthing/releases/download/{version}/syncthing-windows-amd64-{version}.zip"
    
    # Define the target directory and file path
    syncthing_dir = os.path.join('resources', 'syncthing')
    syncthing_exe_path = os.path.join(syncthing_dir, 'syncthing.exe')
    
    # Check if the executable already exists
    if os.path.exists(syncthing_exe_path):
        logging.info("Syncthing executable already exists. Skipping download.")
        return True

    logging.info(f"Syncthing executable not found. Downloading from {url}...")
    
    os.makedirs(syncthing_dir, exist_ok=True)
    
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status() # Raise an exception for bad status codes
        
        # Use a BytesIO object to handle the zip file in memory
        with zipfile.ZipFile(io.BytesIO(response.content)) as zip_ref:
            # Find the executable within the zip
            for file_info in zip_ref.infolist():
                if file_info.filename.endswith('syncthing.exe'):
                    logging.info("Found syncthing.exe in zip. Extracting...")
                    # Extract the file directly to the target path
                    with open(syncthing_exe_path, 'wb') as f:
                        f.write(zip_ref.read(file_info.filename))
                    logging.info("Syncthing executable downloaded and extracted successfully.")
                    return True
        
        logging.error("syncthing.exe was not found inside the downloaded zip file.")
        return False
        
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to download Syncthing: {e}")
        return False
    except zipfile.BadZipFile:
        logging.error("Downloaded file is not a valid zip archive.")
        return False

if __name__ == '__main__':
    syncthing_version = get_config_value('syncthing_version')

    try:
        with open('pyproject.toml', 'r') as f:
            project_data = toml.load(f)
            app_version = project_data['project']['version']
    except (FileNotFoundError, KeyError) as e:
        logging.error(f"Failed to read app version from pyproject.toml: {e}")
        app_version = None

    if not syncthing_version or not app_version:
        logging.error("Required version information not found. Build aborted.")
    elif not download_syncthing(syncthing_version):
        logging.error("Build process aborted because Syncthing executable could not be downloaded.")
    else:
        # Define the application's entry point
        main_script = 'src/main.py'
        
        # Define the application name
        app_name = 'NydusNet'
        
        # Define any additional data files or directories to include
        data_to_add = [
            os.path.join('resources', 'syncthing'),
            os.path.join('ansible')
        ]
        
        pyinstaller_args = [
            main_script,
            '--name', app_name,
            '--onefile',
            '--windowed',
            '--noconfirm',
        ]
        
        for item in data_to_add:
            pyinstaller_args.extend(['--add-data', f'{item}{os.pathsep}{item}'])
            
        logging.info(f"Running PyInstaller with args: {' '.join(pyinstaller_args)}")
        
        PyInstaller.__main__.run(pyinstaller_args)
