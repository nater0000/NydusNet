import PyInstaller.__main__
import os
import requests
import zipfile
import io
import logging
import toml
import shutil
import tempfile
import sys # Added for sys.platform check

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_config_value(key: str) -> str | None: # Return None if not found
    """Reads a value from the project's pyproject.toml file, located in the parent directory."""
    try:
        # --- CORRECTED PATH LOGIC ---
        script_dir = os.path.dirname(os.path.abspath(__file__)) # Directory of build.py (e.g., .../scripts)
        project_root = os.path.dirname(script_dir) # Parent directory (e.g., ...)
        toml_path = os.path.join(project_root, 'pyproject.toml') # Path to pyproject.toml in the root
        # --- END CORRECTION ---

        logging.debug(f"Attempting to read pyproject.toml from: {toml_path}") # Debug log
        with open(toml_path, 'r', encoding='utf-8') as f: # Specify encoding
            data = toml.load(f)
            # Navigate the TOML structure safely
            value = data.get('tool', {}).get('nydusnet', {}).get(key)
            if value is None:
                logging.warning(f"Key '{key}' not found in [tool.nydusnet] section of {toml_path}")
            return value
    except FileNotFoundError:
        logging.error(f"Failed to find pyproject.toml at {toml_path}")
        return None
    except KeyError as e:
        # This shouldn't happen with .get(), but kept for safety
        logging.error(f"Failed to read '{key}' structure from pyproject.toml: {e}")
        return None
    except Exception as e:
        logging.error(f"An unexpected error occurred reading pyproject.toml: {e}", exc_info=True)
        return None


def download_syncthing(version: str) -> bool: # Explicit return type
    """Downloads and extracts the full Syncthing package if it doesn't already exist."""
    if not version:
        logging.error("No Syncthing version provided. Aborting download.")
        return False

    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir) # Use correct project root
    syncthing_dir = os.path.join(project_root, 'resources', 'syncthing')
    syncthing_exe_path = os.path.join(syncthing_dir, 'syncthing.exe')

    # Construct URL (assuming Windows AMD64 for now, could be made dynamic)
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
        logging.info(f"Downloading Syncthing from {url}...")
        response = requests.get(url, stream=True, timeout=60) # Add timeout
        response.raise_for_status() # Check for HTTP errors (4xx or 5xx)
        logging.info("Download complete. Extracting...")

        with tempfile.TemporaryDirectory() as temp_dir:
            logging.debug(f"Extracting Syncthing zip to temporary directory: {temp_dir}")
            try:
                with zipfile.ZipFile(io.BytesIO(response.content)) as zip_ref:
                    # Find the root directory name inside the zip more robustly
                    root_folders = list(set(f.split('/')[0] for f in zip_ref.namelist() if '/' in f and f.split('/')[0]))
                    if not root_folders:
                        # Case: Files are directly in the zip root (unlikely for Syncthing)
                        logging.warning("Zip file might not have a root folder. Extracting files directly.")
                        source_folder = temp_dir
                        zip_ref.extractall(temp_dir)
                    elif len(root_folders) == 1:
                        # Standard case: Single root folder
                        source_folder = os.path.join(temp_dir, root_folders[0])
                        zip_ref.extractall(temp_dir) # Extract everything
                    else:
                        # Multiple root folders - try to find the one with syncthing.exe
                        logging.warning(f"Zip file has multiple root folders: {root_folders}. Attempting to find syncthing.exe.")
                        source_folder = None
                        zip_ref.extractall(temp_dir) # Extract all to check contents
                        for folder in root_folders:
                            folder_path = os.path.join(temp_dir, folder)
                            if os.path.exists(os.path.join(folder_path, 'syncthing.exe')):
                                source_folder = folder_path
                                logging.info(f"Found syncthing.exe in subfolder: {folder}")
                                break
                        if not source_folder:
                             raise zipfile.BadZipFile("Could not determine correct subfolder containing syncthing.exe in multi-root zip.")

                    logging.debug(f"Determined source folder for copying: {source_folder}")

            except zipfile.BadZipFile as bzfe:
                 logging.error(f"Downloaded file is not a valid zip file or structure is unexpected: {bzfe}")
                 return False
            except IndexError: # Might happen if zip is empty or namelist parsing fails
                 logging.error("Zip file seems empty or has unexpected structure during folder determination.")
                 return False

            if not os.path.isdir(source_folder):
                 logging.error(f"Extracted source folder '{source_folder}' not found in temp directory.")
                 return False

            # Copy all files from the extracted source folder to our target directory
            logging.info(f"Copying files from {source_folder} to {syncthing_dir}")
            copied_files = []
            errors_copying = 0
            for item in os.listdir(source_folder):
                s_path = os.path.join(source_folder, item)
                d_path = os.path.join(syncthing_dir, item)
                try:
                    if os.path.isfile(s_path):
                        shutil.copy2(s_path, d_path) # copy2 preserves metadata
                        copied_files.append(item)
                    # No need to copy dirs for standard Syncthing release zip
                except Exception as copy_e:
                    logging.error(f"Error copying '{item}': {copy_e}")
                    errors_copying += 1
            logging.debug(f"Copied items: {len(copied_files)} files.")
            if errors_copying > 0:
                logging.warning(f"{errors_copying} errors occurred during file copying.")


        if os.path.exists(syncthing_exe_path):
            logging.info("Syncthing package downloaded and extracted successfully.")
            return True
        else:
            logging.error(f"Extraction failed: syncthing.exe not found at {syncthing_exe_path} after copying process.")
            return False

    except requests.exceptions.HTTPError as http_err:
        logging.error(f"HTTP error during Syncthing download: {http_err.response.status_code} - {http_err}")
        return False
    except requests.exceptions.RequestException as req_e:
        logging.error(f"Network error during Syncthing download: {req_e}")
        return False
    except Exception as e: # Catch any other unexpected errors during download/extraction
        logging.error(f"An unexpected error occurred during Syncthing download/extraction: {e}", exc_info=True)
        return False

if __name__ == '__main__':
    # Determine project root relative to this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir) # Project root is parent of /scripts

    logging.info(f"Build script running from: {script_dir}")
    logging.info(f"Project Root determined as: {project_root}")

    # --- Construct source paths relative to project root ---
    # These paths are used for finding files locally AND for --add-data source paths
    syncthing_src_path_rel = os.path.join('resources', 'syncthing')
    images_src_path_rel = os.path.join('resources', 'images')
    main_script_path_rel = os.path.join('src', 'main.py')
    icon_path_rel = os.path.join(images_src_path_rel, 'nydusnet.ico')

    # --- Construct absolute paths needed by PyInstaller ---
    main_script_abs = os.path.join(project_root, main_script_path_rel)
    icon_abs = os.path.join(project_root, icon_path_rel)

    # --- Verify essential source files/dirs exist before proceeding ---
    if not os.path.isfile(main_script_abs):
        logging.error(f"Main script not found at {main_script_abs}. Aborting build.")
        sys.exit(1) # Exit script with error code
    if not os.path.isdir(os.path.join(project_root, images_src_path_rel)):
         logging.warning(f"Images source directory not found at {os.path.join(project_root, images_src_path_rel)}. Icons might be missing.")
         # Allow build to continue, but log warning
    if not os.path.isfile(icon_abs):
         logging.warning(f"Application icon not found at {icon_abs}. Default icon will be used.")
         # Allow build to continue


    # --- Read Syncthing version ---
    syncthing_version = get_config_value('syncthing_version')
    if not syncthing_version:
        logging.error("Build aborted: Syncthing version not found in pyproject.toml.")
        sys.exit(1)
    # --- Download Syncthing ---
    elif not download_syncthing(syncthing_version):
        logging.error("Build process aborted because Syncthing could not be downloaded/extracted.")
        sys.exit(1)
    # --- Syncthing Download/Extraction Successful ---
    else:
        # --- Define PyInstaller arguments ---
        # Paths for --add-data should be relative to the CWD where pyinstaller runs (project root)
        # Destination paths are relative within the bundle.
        # Use os.pathsep for --add-data separator (';' on Win, ':' on Unix)
        add_data_sep = os.pathsep

        pyinstaller_args = [
            main_script_abs, # Use absolute path to main script
            '--name', 'NydusNet',
            '--onefile',
            '--windowed', # No console window
            '--noconfirm', # Overwrite previous builds without asking
            '--clean', # Clean cache before build
            # --- Add Syncthing data ---
            # Source path relative to CWD, Destination relative to bundle root
            '--add-data', f'{syncthing_src_path_rel}{add_data_sep}resources/syncthing',
            # --- Add Image data ---
            '--add-data', f'{images_src_path_rel}{add_data_sep}resources/images',
            # --- Add Icon ---
             '--icon', icon_abs # Use absolute path for icon
        ]

        logging.info(f"Running PyInstaller with args: {' '.join(pyinstaller_args)}")

        # --- IMPORTANT: Change CWD to project root before running PyInstaller ---
        original_cwd = os.getcwd()
        try:
            os.chdir(project_root) # Change CWD to where pyproject.toml, resources, src are
            logging.info(f"Changed CWD to: {project_root} for PyInstaller")

            # --- Run PyInstaller ---
            PyInstaller.__main__.run(pyinstaller_args)
            logging.info("PyInstaller build complete.")

            # --- Optional: Move output ---
            # output_dir = os.path.join(project_root, 'dist') # Default PyInstaller output
            # final_exe_name = 'NydusNet.exe'
            # final_exe_path = os.path.join(output_dir, final_exe_name)
            # if os.path.exists(final_exe_path):
            #      logging.info(f"Build successful. Executable created at: {final_exe_path}")
            # else:
            #      logging.error("Build finished but final executable was not found!")

        except SystemExit as e:
             # PyInstaller often uses SystemExit on completion/error
             if e.code == 0:
                 logging.info("PyInstaller exited successfully.")
             else:
                 logging.error(f"PyInstaller exited with error code {e.code}.")
                 sys.exit(e.code) # Propagate error code
        except Exception as build_e:
            logging.error(f"PyInstaller build failed with an unexpected error: {build_e}", exc_info=True)
            sys.exit(1) # Exit with error code
        finally:
            os.chdir(original_cwd) # Change back to original CWD
            logging.info(f"Restored CWD to: {original_cwd}")