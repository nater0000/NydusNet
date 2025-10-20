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
        # Ensure the script looks for pyproject.toml relative to its own location
        script_dir = os.path.dirname(os.path.abspath(__file__))
        toml_path = os.path.join(script_dir, 'pyproject.toml') # Construct absolute path
        with open(toml_path, 'r') as f:
            data = toml.load(f)
            # Navigate the TOML structure correctly
            return data.get('tool', {}).get('nydusnet', {}).get(key)
    except FileNotFoundError:
        logging.error(f"Failed to find pyproject.toml at {toml_path}")
        return None
    except KeyError as e:
        logging.error(f"Failed to read '{key}' structure from pyproject.toml: {e}")
        return None
    except Exception as e:
        logging.error(f"An unexpected error occurred reading pyproject.toml: {e}")
        return None


def download_syncthing(version: str):
    """Downloads and extracts the full Syncthing package if it doesn't already exist."""
    if not version:
        logging.error("No Syncthing version provided. Aborting download.")
        return False

    script_dir = os.path.dirname(os.path.abspath(__file__)) # Get script's dir
    # Construct paths relative to the script's dir or project root
    project_root = os.path.dirname(script_dir) if os.path.basename(script_dir) == 'scripts' else script_dir # Adjust if build.py is in a 'scripts' folder
    syncthing_dir = os.path.join(project_root, 'resources', 'syncthing')
    syncthing_exe_path = os.path.join(syncthing_dir, 'syncthing.exe')

    url = f"https://github.com/syncthing/syncthing/releases/download/{version}/syncthing-windows-amd64-{version}.zip"

    if os.path.exists(syncthing_exe_path):
        logging.info(f"Syncthing executable already exists at {syncthing_exe_path}. Skipping download.")
        return True

    logging.info(f"Syncthing not found. Downloading and extracting from {url} to {syncthing_dir}...")
    try:
        os.makedirs(syncthing_dir, exist_ok=True) # Ensure target dir exists
    except OSError as e:
        logging.error(f"Failed to create directory {syncthing_dir}: {e}")
        return False


    try:
        response = requests.get(url, stream=True, timeout=60) # Add timeout
        response.raise_for_status() # Check for HTTP errors

        with tempfile.TemporaryDirectory() as temp_dir:
            logging.debug(f"Extracting Syncthing zip to temporary directory: {temp_dir}")
            try:
                with zipfile.ZipFile(io.BytesIO(response.content)) as zip_ref:
                    # Find the root directory name inside the zip
                    root_folders = list(set(f.split('/')[0] for f in zip_ref.namelist()))
                    if len(root_folders) != 1:
                         logging.warning(f"Zip file has unexpected structure (multiple roots?): {root_folders}. Assuming first contains syncthing.exe.")
                         # Attempt to find the correct folder anyway
                         source_folder = None
                         for folder in root_folders:
                             if any('syncthing.exe' in name for name in zip_ref.namelist() if name.startswith(folder)):
                                 source_folder = os.path.join(temp_dir, folder)
                                 break
                         if not source_folder:
                              raise zipfile.BadZipFile("Could not determine correct subfolder containing syncthing.exe")
                    else:
                        source_folder = os.path.join(temp_dir, root_folders[0])

                    logging.debug(f"Determined source folder inside zip: {source_folder}")
                    zip_ref.extractall(temp_dir) # Extract everything first

            except zipfile.BadZipFile as bzfe:
                 logging.error(f"Downloaded file is not a valid zip file: {bzfe}")
                 return False
            except IndexError:
                 logging.error("Zip file seems empty or has unexpected structure.")
                 return False

            if not os.path.isdir(source_folder):
                 logging.error(f"Extracted source folder '{source_folder}' not found in temp directory.")
                 return False

            # Copy all files from the extracted folder to our target directory
            logging.info(f"Copying files from {source_folder} to {syncthing_dir}")
            copied_files = []
            for item in os.listdir(source_folder):
                s_path = os.path.join(source_folder, item)
                d_path = os.path.join(syncthing_dir, item)
                try:
                    if os.path.isfile(s_path):
                        shutil.copy2(s_path, d_path)
                        copied_files.append(item)
                    elif os.path.isdir(s_path): # Handle subdirs if needed, though Syncthing zip usually doesn't have relevant ones
                        # shutil.copytree(s_path, d_path, dirs_exist_ok=True)
                        pass # Ignore dirs for now unless needed
                except Exception as copy_e:
                    logging.error(f"Error copying {item}: {copy_e}")
            logging.debug(f"Copied items: {copied_files}")


        if os.path.exists(syncthing_exe_path):
            logging.info("Syncthing package downloaded and extracted successfully.")
            return True
        else:
            logging.error(f"Extraction failed: syncthing.exe not found at {syncthing_exe_path} after process.")
            return False

    except requests.exceptions.RequestException as req_e:
        logging.error(f"Failed during Syncthing download: {req_e}")
        return False
    except Exception as e: # Catch any other unexpected errors
        logging.error(f"An unexpected error occurred during Syncthing download/extraction: {e}", exc_info=True)
        return False

if __name__ == '__main__':
    # Determine project root relative to this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir) if os.path.basename(script_dir) == 'scripts' else script_dir

    # --- Construct full paths for resources relative to project root ---
    syncthing_src_path = os.path.join('resources', 'syncthing')
    images_src_path = os.path.join('resources', 'images')
    main_script_path = os.path.join('src', 'main.py')
    icon_path = os.path.join(images_src_path, 'nydusnet.ico') # Path to icon file

    # --- Read Syncthing version ---
    syncthing_version = get_config_value('syncthing_version')
    if not syncthing_version:
        logging.error("Build aborted: Syncthing version not found in pyproject.toml.")
    # --- Download Syncthing ---
    elif not download_syncthing(syncthing_version):
        logging.error("Build process aborted because Syncthing could not be downloaded.")
    else:
        # --- Define PyInstaller arguments ---
        pyinstaller_args = [
            os.path.join(project_root, main_script_path), # Use full path to main script
            '--name', 'NydusNet',
            '--onefile',
            '--windowed',
            '--noconfirm',
            '--clean',
            # --- Add Syncthing data ---
            # Source path is relative to project root, Destination is relative within bundle
            '--add-data', f'{syncthing_src_path}{os.pathsep}resources/syncthing',
            # --- ADD IMAGE DATA ---
            # Source path relative to project root, Destination relative within bundle
            '--add-data', f'{images_src_path}{os.pathsep}resources/images',
            # --- ADD ICON ---
            '--icon', os.path.join(project_root, icon_path) # Use full path to icon
        ]

        logging.info(f"Project Root: {project_root}")
        logging.info(f"Running PyInstaller with args: {' '.join(pyinstaller_args)}")

        # --- Change directory for PyInstaller if needed, or ensure paths are absolute/relative correctly ---
        # It's often best to run PyInstaller from the project root.
        # If build.py is elsewhere, you might need os.chdir(project_root) before running,
        # or ensure all paths in pyinstaller_args are correctly relative to the CWD.
        # The current approach uses full/relative paths directly which should work from anywhere.

        try:
            PyInstaller.__main__.run(pyinstaller_args)
            logging.info("PyInstaller build complete.")
            # Optional: Move the final executable if desired
            # src_exe = os.path.join('dist', 'NydusNet.exe')
            # dst_exe = os.path.join(project_root, 'NydusNet_Standalone.exe')
            # if os.path.exists(src_exe):
            #    shutil.move(src_exe, dst_exe)
            #    logging.info(f"Moved executable to {dst_exe}")

        except Exception as build_e:
            logging.error(f"PyInstaller build failed: {build_e}", exc_info=True)
            