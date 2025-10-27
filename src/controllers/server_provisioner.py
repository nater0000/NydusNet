import logging
import os
import tempfile
import re # Added for regex checks
import time # Added for sleeps
import sys # Added for sys._MEIPASS
from fabric import Connection
from invoke.exceptions import UnexpectedExit, CommandTimedOut
from io import BytesIO
from jinja2 import Environment, FileSystemLoader # Added for templating

class ServerProvisioner:
    """
    Handles the one-time provisioning of a remote server using Fabric,
    replicating the setup logic from the original Ansible playbook.
    """
    def __init__(self, host, admin_user, admin_password, tunnel_user_public_key_string, certbot_email):
        """
        Initializes the provisioner.

        Args:
            host (str): The server's IP address or hostname.
            admin_user (str): The administrative (sudo-capable) user to connect as.
            admin_password (str): The password for the admin_user.
            tunnel_user_public_key_string (str): The public key content for the 'tunnel' user.
            certbot_email (str): Email address for Let's Encrypt registration.
        """
        self.host = host
        self.admin_user = admin_user # Changed from 'user' for clarity
        self.admin_password = admin_password # Changed from 'password'
        self.tunnel_user_public_key_string = tunnel_user_public_key_string # Renamed
        self.certbot_email = certbot_email
        self.log_output = []
        self.tunnel_user = "tunnel" # The restricted user for tunnels

        # --- DETERMINE TEMPLATE DIRECTORY PATH ---
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            # Running packaged: templates are in resources/server-setup inside _MEIPASS
            base_path = sys._MEIPASS
            self.template_dir = os.path.join(base_path, 'resources', 'server-setup')
            logging.info(f"Running packaged. Template path: {self.template_dir}")
        else:
            # Running as script: determine path relative to this file
            self.script_dir = os.path.dirname(os.path.abspath(__file__)) # .../src/controllers
            project_root = os.path.dirname(os.path.dirname(self.script_dir)) # Go up two levels to project root
            self.template_dir = os.path.join(project_root, 'resources', 'server-setup')
            logging.info(f"Running script. Template path: {self.template_dir}")

        # Verify template directory exists - Raise error if not found
        if not os.path.isdir(self.template_dir):
             logging.error(f"Template directory NOT FOUND at: {self.template_dir}")
             raise FileNotFoundError(f"Template directory not found at {self.template_dir}. Ensure 'resources/server-setup' exists and is bundled.")

        try:
            # Load templates from the determined directory
            self.jinja_env = Environment(loader=FileSystemLoader(self.template_dir), autoescape=False)
            logging.debug("Jinja2 environment initialized successfully.")
        except Exception as e:
            logging.error(f"Failed to initialize Jinja2 environment: {e}", exc_info=True)
            raise RuntimeError(f"Failed to set up Jinja2 templating: {e}") from e
        # --- END PATH DETERMINATION ---


    def _log(self, message):
        """Helper to log messages."""
        logging.info(f"[Provisioner:{self.host}] {message}")
        self.log_output.append(message)

    def provision_vps(self) -> tuple[bool, list[str]]:
        """
        Main entry point to perform full VPS provisioning based on Ansible playbook.
        Connects as the admin user.
        """
        self._log(f"Starting full VPS provisioning for {self.host} as '{self.admin_user}'...")
        try:
            with Connection(host=self.host, user=self.admin_user, connect_kwargs={"password": self.admin_password}) as c:
                self._log("Admin connection successful.")

                # Run setup steps sequentially, checking return values
                if not self._install_packages(c): return False, self.log_output
                if not self._ensure_tunnel_user_exists(c): return False, self.log_output
                if not self._deploy_tunnel_user_key(c): return False, self.log_output
                if not self._deploy_setup_tunnel_script(c): return False, self.log_output
                if not self._grant_sudo_permissions(c): return False, self.log_output
                if not self._create_webroot(c): return False, self.log_output
                if not self._configure_firewall(c): return False, self.log_output
                if not self._ensure_nginx_running(c): return False, self.log_output
                # Note: Heartbeat configuration excluded

                self._log("\n✅ Full VPS provisioning completed successfully!")
                return True, self.log_output
        except Exception as e:
            self._log(f"\n❌ A critical error occurred during provisioning: {e}")
            logging.error(f"Provisioning failed for {self.host}", exc_info=True)
            return False, self.log_output

    def _install_packages(self, c: Connection) -> bool:
        """Updates apt cache and installs required packages."""
        self._log("Updating package cache and installing required packages...")
        packages = [
            "nginx", "certbot", "python3-certbot-nginx",
            "fail2ban", "ufw", "lsof" # Added lsof for port checks
        ]
        try:
            # Run update and install in one command
            c.sudo("apt-get update && apt-get install -y " + " ".join(packages), hide=True)
            self._log("Packages installed successfully.")
            return True
        except UnexpectedExit as e:
            self._log(f"❌ Failed to install packages: {e}")
            return False

    def _ensure_tunnel_user_exists(self, c: Connection) -> bool:
        """Checks if the tunnel user exists and creates it if not."""
        self._log(f"Checking for tunnel user '{self.tunnel_user}'...")
        try:
            c.run(f'id {self.tunnel_user}', hide=True)
            self._log(f"User '{self.tunnel_user}' already exists.")
            return True
        except UnexpectedExit:
            self._log(f"User '{self.tunnel_user}' not found. Creating user...")
            try:
                # Create user, lock password, create home dir (-m), set bash shell (-s)
                c.sudo(f'useradd -m -s /bin/bash -p "*" {self.tunnel_user}', hide=True) # -p * locks password
                self._log("User created successfully.")
                return True
            except Exception as e:
                self._log(f"❌ Failed to create user '{self.tunnel_user}': {e}")
                return False
            
    def _deploy_tunnel_user_key(self, c: Connection) -> bool:
        """Installs the public key to the tunnel user's authorized_keys file with command restriction."""
        self._log(f"Configuring authorized key for '{self.tunnel_user}'...")
        authorized_keys_path = f"/home/{self.tunnel_user}/.ssh/authorized_keys"
        ssh_dir_path = f"/home/{self.tunnel_user}/.ssh"

        key_options = f'command="/usr/local/bin/setup_tunnel.sh; sleep infinity",no-agent-forwarding,no-X11-forwarding,no-pty'
        # Ensure key string has no leading/trailing whitespace just in case
        key_line_to_check = f'{key_options} {self.tunnel_user_public_key_string.strip()}'
        # Ensure the line written *ends* with a newline for consistency
        key_line_to_write = key_line_to_check + "\n"


        try:
            # Step 1 & 2 (Unchanged)
            self._log("Step 1: Ensuring .ssh directory exists...")
            c.sudo(f'mkdir -p {ssh_dir_path}', user=self.tunnel_user, hide=True)
            self._log("Step 1: Directory ensured.")
            self._log("Step 2: Setting permissions on .ssh directory...")
            c.sudo(f'chmod 700 {ssh_dir_path}', user=self.tunnel_user, hide=True)
            self._log("Step 2: Directory permissions set (700).")

            # --- Step 3: Check if key already exists (via SFTP) ---
            self._log(f"Step 3: Checking for existing key line in {authorized_keys_path} via SFTP...")
            key_found = False
            try:
                # Use BytesIO to simulate a file for get()
                file_obj = BytesIO()
                # Use c.get() to download the file content
                c.get(authorized_keys_path, file_obj)
                # Decode content (assuming UTF-8, adjust if needed)
                file_content = file_obj.getvalue().decode('utf-8', errors='ignore')
                file_obj.close() # Close the BytesIO object

                # Check if the exact line exists in the content
                # Split lines and strip any trailing whitespace for comparison
                lines_in_file = [line.strip() for line in file_content.splitlines()]
                if key_line_to_check in lines_in_file:
                    key_found = True
                    self._log("Step 3: Exact key line found via SFTP read.")
                else:
                    self._log("Step 3: Key line not found via SFTP read.")

            except FileNotFoundError:
                self._log(f"Step 3: {authorized_keys_path} not found via SFTP (will create).")
                key_found = False # File doesn't exist, so key isn't there
            except Exception as sftp_e:
                 self._log(f"❌ Step 3: Error reading {authorized_keys_path} via SFTP: {sftp_e}")
                 # Decide how to handle SFTP errors - fail safe or assume not found?
                 # Let's assume not found and try to write, but log the error.
                 logging.error(f"SFTP read error for {authorized_keys_path}", exc_info=True)
                 key_found = False
                 self._log("Step 3: Proceeding assuming key not found due to SFTP error.")
            # --- End SFTP Check ---


            if key_found:
                # --- Key Found Path ---
                self._log("Step 3a: Skipping write, key already present.")
                # Proceed to final permission checks

            else:
                # --- Key Not Found / SFTP Error Path ---
                self._log("Step 3b: Installing/Overwriting authorized_keys...")
                # Use SFTP put for potentially more reliable writing than echo | tee
                # Create a BytesIO object with the line *including newline*
                key_file_obj = BytesIO(key_line_to_write.encode('utf-8'))

                self._log(f"Step 3c: Uploading key line to {authorized_keys_path} via SFTP...")
                # Upload the content using c.put()
                c.put(key_file_obj, authorized_keys_path)
                key_file_obj.close()
                self._log("Step 3d: Upload finished.")

                # *** Important: `c.put` uses the admin user, need to set owner/perms AFTER ***
                self._log("Step 3e: Setting owner/group for uploaded key file...")
                c.sudo(f'chown {self.tunnel_user}:{self.tunnel_user} {authorized_keys_path}', hide=True)
                self._log("Step 3f: Owner/group set.")

                # Permissions will be set in Step 4

                self._log("Authorized key configured successfully.")


            # Step 4 & 5 (Set permissions and ownership - crucial after SFTP put)
            self._log(f"Step 4: Setting final permissions on {authorized_keys_path}...")
            # Set permissions as the tunnel user if possible, otherwise admin
            c.sudo(f'chmod 600 {authorized_keys_path}', user=self.tunnel_user, hide=True, timeout=5)
            self._log("Step 4: File permissions set (600).")

            self._log(f"Step 5: Ensuring ownership of {ssh_dir_path} and contents...")
            c.sudo(f'chown -R {self.tunnel_user}:{self.tunnel_user} {ssh_dir_path}', hide=True, timeout=5)
            self._log("Step 5: Ownership ensured.")

            self._log("✅ Authorized key configuration completed.")
            return True

        # --- Update main exception handler ---
        except CommandTimedOut as e: # Catch timeouts from sudo commands
            self._log(f"❌ Command timed out during key configuration: {e.command}")
            logging.error("Timeout during key deployment", exc_info=True)
            return False
        except Exception as e: # Catch other errors like SFTP issues not caught above
            self._log(f"❌ Failed during authorized key configuration: {e}")
            logging.error("Exception during key deployment", exc_info=True)
            return False
        
    def _deploy_setup_tunnel_script(self, c: Connection) -> bool:
        """Renders and uploads the setup_tunnel.sh script."""
        self._log("Deploying setup_tunnel.sh script...")
        remote_path = "/usr/local/bin/setup_tunnel.sh"
        local_temp_path = None # Ensure variable exists for finally block
        try:
            # Render the Jinja2 template
            template = self.jinja_env.get_template('setup_tunnel.sh.j2')
            rendered_content = template.render(certbot_email=self.certbot_email)

            # Write rendered content to a temporary file
            with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8') as temp_file:
                temp_file.write(rendered_content)
                local_temp_path = temp_file.name

            # Upload the rendered file
            c.put(local_temp_path, remote=remote_path) # Upload first

            # Set ownership and permissions using sudo
            c.sudo(f'chown root:root {remote_path}', hide=True)
            c.sudo(f'chmod 755 {remote_path}', hide=True)

            self._log("setup_tunnel.sh deployed successfully.")
            return True
        except Exception as e:
            self._log(f"❌ Failed to deploy setup_tunnel.sh: {e}")
            return False
        finally:
            # Clean up the temporary file
            if local_temp_path and os.path.exists(local_temp_path):
                os.remove(local_temp_path)

    def _grant_sudo_permissions(self, c: Connection) -> bool:
        """Grants specific NOPASSWD sudo permissions to the tunnel user via sudoers.d."""
        self._log(f"Granting specific sudo permissions to '{self.tunnel_user}'...")
        sudoers_file_path = "/etc/sudoers.d/nydusnet-tunnel"
        # Commands allowed without password
        allowed_commands = [
            "/usr/sbin/nginx -s reload",
            "/usr/sbin/nginx -t",
            "/usr/bin/tee /etc/nginx/sites-available/*",
            "/usr/bin/ln -sfn /etc/nginx/sites-available/* /etc/nginx/sites-enabled/",
            "/usr/bin/certbot *" # Granting broad certbot access
        ]
        sudo_line = f"{self.tunnel_user} ALL=(ALL) NOPASSWD: {', '.join(allowed_commands)}"

        try:
            # Check if the file exists and contains the correct line
            check_cmd = f"test -f {sudoers_file_path} && grep -q -F '{sudo_line}' {sudoers_file_path}"
            result = c.run(check_cmd, warn=True, hide=True)

            if result.ok:
                self._log("Sudo permissions already configured correctly.")
                return True
            else:
                self._log("Configuring sudo permissions...")
                # Use tee to write the line to the file (creates or overwrites)
                c.sudo(f'sh -c \'echo "{sudo_line}" | tee {sudoers_file_path}\'', hide=True)
                c.sudo(f'chmod 440 {sudoers_file_path}', hide=True) # Secure permissions
                self._log("Sudo permissions granted.")
                return True
        except Exception as e:
            self._log(f"❌ Failed to grant sudo permissions: {e}")
            return False

    def _create_webroot(self, c: Connection) -> bool:
        """Creates the webroot directory for Certbot challenges."""
        self._log("Creating webroot directory for Certbot...")
        webroot_path = "/var/www/html"
        try:
            c.sudo(f'mkdir -p {webroot_path}', hide=True)
            c.sudo(f'chmod 755 {webroot_path}', hide=True) # Standard permissions
            self._log("Webroot directory created.")
            return True
        except Exception as e:
            self._log(f"❌ Failed to create webroot directory: {e}")
            return False

    def _configure_firewall(self, c: Connection) -> bool:
        """Configures UFW to allow SSH, HTTP, and HTTPS."""
        self._log("Configuring firewall (UFW)...")
        try:
            # Check if ufw is active first
            status_result = c.sudo('ufw status', hide=True, warn=True)
            is_active = 'Status: active' in status_result.stdout

            # Allow necessary services/ports
            c.sudo('ufw allow OpenSSH', hide=True)
            c.sudo('ufw allow "Nginx Full"', hide=True) # Handles 80 and 443
            self._log("Firewall rules for SSH and Nginx added/updated.")

            if not is_active:
                self._log("Enabling firewall...")
                c.sudo('ufw --force enable', hide=True) # Use --force for non-interactive
                self._log("Firewall enabled.")
            else:
                 self._log("Firewall is already active.")
            return True
        except Exception as e:
            self._log(f"❌ Failed to configure firewall: {e}")
            return False

    def _ensure_nginx_running(self, c: Connection) -> bool:
        """Ensures the Nginx service is started and enabled on boot."""
        self._log("Ensuring Nginx service is running and enabled...")
        try:
            # Use systemctl if available
            if c.run('command -v systemctl', hide=True, warn=True).ok:
                c.sudo('systemctl enable nginx', hide=True)
                c.sudo('systemctl start nginx', hide=True)
            # Fallback for older systems (less likely but possible)
            elif c.run('command -v update-rc.d', hide=True, warn=True).ok:
                 c.sudo('update-rc.d nginx defaults', hide=True)
                 c.sudo('service nginx start', hide=True)
            else:
                 self._log("❌ Could not determine service manager (systemctl or service). Cannot manage Nginx service.")
                 return False

            self._log("Nginx service is started and enabled.")
            return True
        except Exception as e:
            self._log(f"❌ Failed to start/enable Nginx service: {e}")
            return False

    # --- Methods below are for potential use with admin credentials, ---
    # --- NOT intended for regular TunnelManager operations. ---

    def check_port_status(self, port: int) -> tuple[bool, dict | None, str]:
        """
        Checks if a given port is in use on the remote server using admin credentials.
        Returns a tuple: (success, process_info, message).
        process_info format: {'pid': '1234', 'command': 'sshd', 'user': 'tunnel'}
        """
        self._log(f"[Admin Check] Checking status of port {port} on {self.host} as '{self.admin_user}'...")
        try:
            with Connection(host=self.host, user=self.admin_user, connect_kwargs={"password": self.admin_password}) as c:
                # Use lsof: -iTCP:port, -sTCP:LISTEN, -P (no port names), -n (no host names)
                # Use sudo as the process may be owned by another user (like 'tunnel')
                # -Fpcu outputs parsable lines: p<PID>, c<COMMAND>, u<USER>
                result = c.sudo(f'lsof -iTCP:{port} -sTCP:LISTEN -P -n -Fpcu', warn=True, hide=True)

                if result.failed or not result.stdout.strip():
                    msg = f"Port {port} is free."
                    self._log(f"[Admin Check] {msg}")
                    return True, None, msg

                lines = result.stdout.strip().split('\n')
                info = {}
                current_pid = None
                # Parse the -Fpcu output (e.g., p1234, csshd, u-tunnel)
                # Assumes output per process starts with 'p'
                for line in lines:
                    if not line: continue
                    type_char = line[0]
                    value = line[1:]
                    if type_char == 'p':
                        current_pid = value
                        info = {'pid': current_pid} # Start new info dict for this PID
                    elif current_pid: # Only add if we have a current PID context
                        if type_char == 'c': info['command'] = value
                        if type_char == 'u': info['user'] = value

                # Return the info for the *last* process found (usually only one listener)
                if 'pid' in info:
                    msg = f"Port {port} is in use by PID {info['pid']} ({info.get('command', 'N/A')}, user {info.get('user', 'N/A')})."
                    self._log(f"[Admin Check] {msg}")
                    return True, info, msg
                else:
                    # Fallback if parsing fails but output was found
                    self._log(f"[Admin Check] Port {port} is in use, but PID/details could not be reliably parsed.")
                    return True, {'pid': 'Unknown'}, "Port in use, details unknown"

        except Exception as e:
            msg = f"❌ Failed to check port {port} using admin creds: {e}"
            self._log(f"[Admin Check] {msg}")
            logging.error(msg, exc_info=True)
            return False, None, msg


    def kill_process_on_port(self, port: int) -> tuple[bool, str]:
        """Finds and kills the process listening on the given port using admin credentials."""
        success, info, msg = self.check_port_status(port) # Uses admin creds implicitly
        if not success:
            return False, f"Could not check port status before killing: {msg}"
        if not info or 'pid' not in info:
            return True, f"No process found to kill on port {port}."

        pid = info['pid']
        if pid == 'Unknown':
             return False, "Cannot kill process: PID is unknown."

        self._log(f"[Admin Action] Attempting to kill process with PID {pid} on port {port}...")
        try:
            with Connection(host=self.host, user=self.admin_user, connect_kwargs={"password": self.admin_password}) as c:
                c.sudo(f'kill -9 {pid}', hide=True) # Force kill
                msg = f"Successfully killed process {pid} on port {port}."
                self._log(f"[Admin Action] {msg}")
                # Verify it's gone
                time.sleep(0.5)
                success, info_after, _ = self.check_port_status(port)
                if success and not info_after:
                    self._log("[Admin Action] Verified process is no longer listening.")
                else:
                    self._log("[Admin Action] Warning: Process may not have been killed or another took its place.")
                return True, msg
        except Exception as e:
            msg = f"❌ Failed to kill process {pid} using admin creds: {e}"
            self._log(f"[Admin Action] {msg}")
            logging.error(msg, exc_info=True)
            return False, msg