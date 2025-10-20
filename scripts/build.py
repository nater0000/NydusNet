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
    """Reads a value from the project's pyproject.toml file, located in the parent directory."""
    try:
        # --- CORRECTED PATH LOGIC ---
        script_dir = os.path.dirname(os.path.abspath(__file__)) # Directory of build.py (e.g., .../scripts)
        project_root = os.path.dirname(script_dir) # Parent directory (e.g., ...)
        toml_path = os.path.join(project_root, 'pyproject.toml') # Path to pyproject.toml in the root
        # --- END CORRECTION ---

        logging.debug(f"Attempting to read pyproject.toml from: {toml_path}") # Debug log
        with open(toml_path, 'r') as f:
            data = toml.load(f)
            # Navigate the TOML structure safely
            return data.get('tool', {}).get('nydusnet', {}).get(key)
    except FileNotFoundError:
        logging.error(f"Failed to find pyproject.toml at {toml_path}")
        return None
    except KeyError as e:
        logging.error(f"Failed to read '{key}' structure from pyproject.toml: {e}")
        return None
    except Exception as e:
        logging.error(f"An unexpected error occurred reading pyproject.toml: {e}", exc_info=True)
        return None


def download_syncthing(version: str):
    """Downloads and extracts the full Syncthing package if it doesn't already exist."""
    if not version:
        logging.error("No Syncthing version provided. Aborting download.")
        return False

    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir) # Use correct project root
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
                    root_folders = list(set(f.split('/')[0] for f in zip_ref.namelist() if '/' in f)) # More robust check for folders
                    if not root_folders:
                        # Handle case where zip might not have a root folder (unlikely for Syncthing)
                        logging.warning("Zip file might not have a root folder. Extracting directly.")
                        source_folder = temp_dir # Extract directly to temp_dir
                        zip_ref.extractall(temp_dir)
                    elif len(root_folders) == 1:
                        source_folder = os.path.join(temp_dir, root_folders[0])
                        zip_ref.extractall(temp_dir) # Extract everything first
                    else: # Handle multiple root folders if necessary (unlikely)
                         logging.warning(f"Zip file has multiple root folders: {root_folders}. Attempting to find syncthing.exe.")
                         source_folder = None
                         for folder in root_folders:
                             folder_path = os.path.join(temp_dir, folder)
                             zip_ref.extractall(temp_dir) # Extract needed for checking content
                             if os.path.exists(os.path.join(folder_path, 'syncthing.exe')):
                                 source_folder = folder_path
                                 logging.info(f"Found syncthing.exe in subfolder: {folder}")
                                 break
                         if not source_folder:
                              raise zipfile.BadZipFile("Could not determine correct subfolder containing syncthing.exe in multi-root zip.")

                    logging.debug(f"Determined source folder for copying: {source_folder}")

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
                    # No need to copy dirs for standard Syncthing release zip
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
    project_root = os.path.dirname(script_dir) # Project root is parent of /scripts

    # --- Construct source paths relative to project root ---
    syncthing_src_path_rel = os.path.join('resources', 'syncthing')
    images_src_path_rel = os.path.join('resources', 'images')
    main_script_path_rel = os.path.join('src', 'main.py')
    icon_path_rel = os.path.join(images_src_path_rel, 'nydusnet.ico')

    # --- Read Syncthing version ---
    syncthing_version = get_config_value('syncthing_version')
    if not syncthing_version:
        logging.error("Build aborted: Syncthing version not found in pyproject.toml.")
    # --- Download Syncthing ---
    elif not download_syncthing(syncthing_version):
        logging.error("Build process aborted because Syncthing could not be downloaded.")
    else:
        # --- Define PyInstaller arguments ---
        # Paths for --add-data should be relative to the CWD where pyinstaller runs (project root)
        # Destination paths are relative within the bundle.
        pyinstaller_args = [
            os.path.join(project_root, main_script_path_rel), # Use absolute path to main script
            '--name', 'NydusNet',
            '--onefile',
            '--windowed',
            '--noconfirm',
            '--clean',
            # --- Add Syncthing data ---
            # Source path relative to CWD, Destination relative to bundle root
            '--add-data', f'{syncthing_src_path_rel}{os.pathsep}resources/syncthing',
            # --- Add Image data ---
            '--add-data', f'{images_src_path_rel}{os.pathsep}resources/images',
            # --- Add Icon ---
             '--icon', os.path.join(project_root, icon_path_rel) # Use absolute path for icon
        ]

        logging.info(f"Project Root: {project_root}")
        logging.info(f"Running PyInstaller with args: {' '.join(pyinstaller_args)}")

        # --- IMPORTANT: Change CWD to project root before running PyInstaller ---
        original_cwd = os.getcwd()
        try:
            os.chdir(project_root) # Change CWD to where pyproject.toml, resources, src are
            logging.info(f"Changed CWD to: {project_root}")
            PyInstaller.__main__.run(pyinstaller_args)
            logging.info("PyInstaller build complete.")
        except Exception as build_e:
            logging.error(f"PyInstaller build failed: {build_e}", exc_info=True)
        finally:
            os.chdir(original_cwd) # Change back to original CWD
            logging.info(f"Restored CWD to: {original_cwd}")