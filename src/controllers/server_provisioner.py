import logging
from fabric import Connection
from invoke.exceptions import UnexpectedExit

class ServerProvisioner:
    """
    Handles the one-time provisioning of a remote server using Fabric.
    """
    def __init__(self, host, user, password, public_key_string):
        self.host = host
        self.user = user
        self.password = password
        self.public_key_string = public_key_string
        self.log_output = []
        self.tunnel_user = "tunnel"

    def _log(self, message):
        logging.info(f"[Provisioner] {message}")
        self.log_output.append(message)

    def run(self) -> tuple[bool, list[str]]:
        self._log(f"Connecting to {self.host} as '{self.user}'...")
        try:
            with Connection(host=self.host, user=self.user, connect_kwargs={"password": self.password}) as c:
                self._log("Connection successful.")
                if not self._ensure_user_exists(c): return False, self.log_output
                if not self._ensure_ssh_key_installed(c): return False, self.log_output
                if not self._ensure_permissions(c): return False, self.log_output
                if not self._configure_sshd(c): return False, self.log_output
                self._log("\n✅ Server provisioning completed successfully!")
                return True, self.log_output
        except Exception as e:
            self._log(f"\n❌ A critical error occurred: {e}")
            logging.error(f"Provisioning failed", exc_info=True)
            return False, self.log_output

    def _ensure_user_exists(self, c: Connection) -> bool:
        self._log(f"Checking for user '{self.tunnel_user}'...")
        try:
            c.run(f'id {self.tunnel_user}', hide=True)
            self._log(f"User '{self.tunnel_user}' already exists.")
            return True
        except UnexpectedExit:
            self._log(f"User '{self.tunnel_user}' not found. Creating user...")
            try:
                c.sudo(f'useradd -m -s /bin/bash {self.tunnel_user}')
                self._log("User created successfully.")
                return True
            except Exception as e:
                self._log(f"❌ Failed to create user: {e}")
                return False

    def _ensure_ssh_key_installed(self, c: Connection) -> bool:
        self._log("Checking for SSH public key installation...")
        authorized_keys_path = f"/home/{self.tunnel_user}/.ssh/authorized_keys"
        try:
            c.sudo(f'mkdir -p /home/{self.tunnel_user}/.ssh', user=self.tunnel_user)
            result = c.run(f'grep -q -F "{self.public_key_string}" {authorized_keys_path}', warn=True, hide=True)
            if result.ok:
                self._log("Public key is already installed.")
                return True
            else:
                self._log("Public key not found. Installing key...")
                # Use a standard shell command to append the key.
                # The outer single quotes prevent the shell from interpreting the key string.
                c.sudo(f'sh -c \'echo "{self.public_key_string}" >> {authorized_keys_path}\'')
                c.sudo(f'chown {self.tunnel_user}:{self.tunnel_user} {authorized_keys_path}')
                self._log("Public key installed successfully.")
                return True
        except Exception as e:
            self._log(f"❌ Failed to install public key: {e}")
            return False

    def _ensure_permissions(self, c: Connection) -> bool:
        self._log("Verifying SSH directory permissions...")
        try:
            c.sudo(f'chmod 700 /home/{self.tunnel_user}/.ssh', user=self.tunnel_user)
            c.sudo(f'chmod 600 /home/{self.tunnel_user}/.ssh/authorized_keys', user=self.tunnel_user)
            self._log("Permissions set correctly.")
            return True
        except Exception as e:
            self._log(f"❌ Failed to set permissions: {e}")
            return False

    def _configure_sshd(self, c: Connection) -> bool:
        self._log("Checking SSH server configuration...")
        sshd_config_path = "/etc/ssh/sshd_config"
        config_options = {"AllowTcpForwarding": "yes", "ClientAliveInterval": "60"}
        made_changes = False
        try:
            for key, value in config_options.items():
                result = c.run(f'grep -q "^{key} {value}" {sshd_config_path}', warn=True, hide=True)
                if result.ok:
                    self._log(f"- {key} is already configured correctly.")
                else:
                    self._log(f"- Setting '{key} {value}'...")
                    c.sudo(f"sed -i '/^{key}/d' {sshd_config_path}")
                    # Use a standard shell command to append the config line.
                    c.sudo(f'sh -c \'echo "{key} {value}" >> {sshd_config_path}\'')
                    made_changes = True
            if made_changes:
                self._log("Restarting SSH service to apply changes...")
                c.sudo('systemctl restart sshd')
                self._log("SSH service restarted.")
            return True
        except Exception as e:
            self._log(f"❌ Failed to configure SSH service: {e}")
            return False

