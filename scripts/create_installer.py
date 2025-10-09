import subprocess
import logging
import toml
import os

# Configure basic logging to provide feedback on the process
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_app_version() -> str:
    """
    Reads the application version from the pyproject.toml file.
    """
    try:
        with open('pyproject.toml', 'r') as f:
            project_data = toml.load(f)
            return project_data['project']['version']
    except (FileNotFoundError, KeyError) as e:
        logging.error(f"Failed to read app version from pyproject.toml: {e}")
        return None

def run_installer_compiler(version: str, installer_script: str):
    """
    Runs the Inno Setup Compiler to create the final installer.
    
    Args:
        version: The application version to pass to the installer script.
        installer_script: The path to the .iss file.
    """
    if not os.path.exists(installer_script):
        logging.error(f"Installer script not found at {installer_script}. Aborting.")
        return

    # Pass the version to Inno Setup using a preprocessor flag
    command = ['iscc.exe', f'/DMyAppVersion={version}', installer_script]
    
    try:
        logging.info(f"Running Inno Setup Compiler: {' '.join(command)}")
        # The subprocess is run from the current working directory, which is expected to be the project root
        subprocess.run(command, check=True)
        logging.info("Installer created successfully!")
    except FileNotFoundError:
        logging.error("Inno Setup Compiler (iscc.exe) not found. Please install Inno Setup and add it to your PATH.")
    except subprocess.CalledProcessError as e:
        logging.error(f"Inno Setup Compiler failed with exit code {e.returncode}")

if __name__ == '__main__':
    # The script assumes it's being run from the project's root directory
    app_version = get_app_version()
    installer_script = os.path.join('scripts', 'create_installer.iss')

    if app_version:
        run_installer_compiler(app_version, installer_script)
    else:
        logging.error("Installer creation aborted due to missing version information.")
