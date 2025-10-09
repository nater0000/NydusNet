import subprocess
import logging
import os
import threading
import time

class TunnelManager:
    """
    Manages the lifecycle of all SSH tunnel subprocesses.
    """
    def __init__(self, controller):
        self.controller = controller
        self.active_tunnels = {}  # {tunnel_id: subprocess.Popen_object}
        self.ssh_executable = "C:\\Windows\\System32\\OpenSSH\\ssh.exe"

        # A lock to prevent race conditions when modifying the active_tunnels dict
        self._lock = threading.Lock()
        
        # Start a background thread to monitor the health of active tunnels
        self.monitor_thread = threading.Thread(target=self._monitor_tunnels, daemon=True)
        self.monitor_thread.start()

    def start_tunnel(self, tunnel_id: str) -> bool:
        """Starts a single SSH tunnel process for the given tunnel ID."""
        with self._lock:
            if tunnel_id in self.active_tunnels and self.active_tunnels[tunnel_id].poll() is None:
                logging.warning(f"Tunnel {tunnel_id} is already running.")
                return True

            tunnel_config = self.controller.config_manager.get_object_by_id(tunnel_id)
            if not tunnel_config:
                logging.error(f"Could not start tunnel: No config found for ID {tunnel_id}")
                return False

            server_config = self.controller.config_manager.get_object_by_id(tunnel_config['server_id'])
            if not server_config:
                logging.error(f"Could not start tunnel {tunnel_id}: Server config not found.")
                return False
            
            automation_creds = self.controller.get_automation_credentials()
            ssh_key_path = automation_creds.get('ansible_ssh_private_key_path')
            
            if not ssh_key_path or not os.path.exists(ssh_key_path):
                logging.error(f"Could not start tunnel {tunnel_id}: Shared Ansible SSH key path is not found or invalid.")
                return False

            command = [
                self.ssh_executable,
                '-i', f'"{ssh_key_path}"',
                '-o', "ServerAliveInterval=30",
                '-o', "ExitOnForwardFailure=yes",
                '-o', "StrictHostKeyChecking=no",
                '-o', "UserKnownHostsFile=nul",
                '-R', f"{tunnel_config['remote_port']}:{tunnel_config['local_destination']}",
                f"{server_config['user']}@{server_config['ip_address']}",
                f"\"{tunnel_config['hostname']} {tunnel_config['remote_port']}\""
            ]

            logging.info(f"Starting tunnel for {tunnel_config['hostname']}")
            
            try:
                process = subprocess.Popen(
                    ' '.join(command),
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                self.active_tunnels[tunnel_id] = process
                return True
            except FileNotFoundError:
                logging.error(f"SSH executable not found at '{self.ssh_executable}'. Please install OpenSSH or check your PATH.")
                return False

    def stop_tunnel(self, tunnel_id: str):
        """Stops a single running SSH tunnel process."""
        with self._lock:
            if tunnel_id in self.active_tunnels:
                process = self.active_tunnels.pop(tunnel_id)
                if process.poll() is None: # Check if it's still running
                    logging.info(f"Terminating tunnel process for ID {tunnel_id}")
                    process.terminate()
                else:
                    logging.info(f"Tunnel process for ID {tunnel_id} had already exited.")
            else:
                logging.warning(f"Attempted to stop tunnel {tunnel_id}, but it was not found.")

    def start_all_tunnels(self):
        """Starts all enabled tunnels from the configuration."""
        logging.info("Starting all enabled tunnels...")
        tunnels_to_start = [t for t in self.controller.config_manager.get_tunnels() if t.get('enabled', True)]
        for tunnel in tunnels_to_start:
            self.start_tunnel(tunnel['id'])
        self.controller.refresh_dashboard()

    def stop_all_tunnels(self):
        """Stops all currently active tunnel processes."""
        logging.info("Stopping all active tunnels...")
        for tunnel_id in list(self.active_tunnels.keys()):
            self.stop_tunnel(tunnel_id)
        self.controller.refresh_dashboard()

    def get_tunnel_statuses(self) -> dict:
        """
        Checks the live status of all managed processes.
        Returns a dictionary of {tunnel_id: "running" | "stopped" | "error"}.
        """
        statuses = {}
        with self._lock:
            for tunnel_id, process in self.active_tunnels.items():
                if process.poll() is None:
                    statuses[tunnel_id] = "running"
                else:
                    statuses[tunnel_id] = "error" if process.returncode != 0 else "stopped"
        return statuses

    def _monitor_tunnels(self):
        """
        A background thread that periodically checks for crashed tunnels
        and notifies the UI to refresh.
        """
        while True:
            time.sleep(15)
            needs_refresh = False
            with self._lock:
                # Check for processes that have exited but are still in our active list
                for tunnel_id, process in self.active_tunnels.items():
                    if process.poll() is not None:
                        logging.error(f"Monitor detected unexpected exit for tunnel {tunnel_id}. Status: {process.returncode}")
                        needs_refresh = True
            
            if needs_refresh:
                logging.info("Monitor detected a change in tunnel status. Refreshing dashboard.")
                self.controller.refresh_dashboard()
