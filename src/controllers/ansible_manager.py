import subprocess
import logging
import os
import threading
import tempfile
import json
from collections import namedtuple

# Ansible imports
from ansible.parsing.dataloader import DataLoader
from ansible.vars.manager import VariableManager
from ansible.inventory.manager import InventoryManager
from ansible.executor.playbook_executor import PlaybookExecutor
from ansible.utils.display import Display
from ansible import context
from ansible.plugins.callback import CallbackBase

class NydusNetCallback(CallbackBase):
    """
    A custom callback plugin to stream Ansible output to a UI log_callback.
    """
    def __init__(self, log_callback):
        super().__init__()
        self.log_callback = log_callback
        self.display = Display()
        self.display.verbosity = 3  # Set a high verbosity for detailed logs

    def v2_runner_on_ok(self, result):
        self.log_callback(f"SUCCESS: {result._host.name} => {result._task.get_name()}")
        # Optional: Add details like module output
        # if result._result.get('stdout', ''):
        #    self.log_callback(result._result['stdout'])

    def v2_runner_on_failed(self, result, ignore_errors=False):
        self.log_callback(f"FAILED: {result._host.name} => {result._task.get_name()}")
        if result._result.get('msg', ''):
            self.log_callback(f"  Error: {result._result['msg']}")
        # Also print detailed failure info for debugging
        self.log_callback(json.dumps(result._result, indent=2))
        
    def v2_playbook_on_play_start(self, play):
        self.log_callback(f"\nPLAY [{play.name}]")

    def v2_playbook_on_stats(self, stats):
        # Summarize the playbook run
        self.log_callback("\n--- PLAYBOOK RUN SUMMARY ---")
        hosts = sorted(stats.processed.keys())
        for h in hosts:
            summary = stats.summarize(h)
            self.log_callback(f"{h} : {json.dumps(summary, indent=2)}")

# This is a critical step to properly configure the Ansible context
context.CLIARGS = namedtuple('CLIARGS', [
    'connection', 'module_path', 'forks', 'become', 'become_method',
    'become_user', 'check', 'diff', 'private_key_file', 'remote_user',
    'verbosity', 'extra_vars', 'host_key_checking'
])(
    connection='ssh', module_path=None, forks=10, become=True, become_method='sudo',
    become_user='root', check=False, diff=False, private_key_file=None, remote_user=None,
    verbosity=0, extra_vars=[], host_key_checking=False
)

class AnsibleManager:
    """
    Manages the execution of Ansible playbooks to provision and configure servers.
    """
    def __init__(self, controller):
        self.controller = controller
        
        # In a real app, determine the install path dynamically
        self.install_path = os.getcwd() 
        self.ansible_project_path = os.path.join(self.install_path, 'ansible')
        self.playbook_path = os.path.join(self.ansible_project_path, 'setup_vps.yml')
        
    def provision_server(self, server_id: str, log_callback):
        """
        Runs the main Ansible playbook against a specific server in a background thread.
        
        Args:
            server_id: The ID of the server to provision.
            log_callback: A function from the UI to send real-time log output to.
        """
        server_config = self.controller.config_manager.get_object_by_id(server_id)
        if not server_config:
            log_callback(f"ERROR: Server with ID {server_id} not found.")
            return

        # Decrypt and get the vault password from the main controller
        vault_pass = self.controller.get_decrypted_vault_password()
        if not vault_pass:
            log_callback("ERROR: Could not retrieve Ansible Vault password. Is the app unlocked?")
            return

        # Start the playbook execution in a separate thread to keep the UI responsive
        thread = threading.Thread(
            target=self._run_playbook_thread,
            args=(server_config, vault_pass, log_callback)
        )
        thread.daemon = True
        thread.start()

    def _run_playbook_thread(self, server_config: dict, vault_pass: str, log_callback):
        """The actual playbook execution logic that runs in a background thread."""
        log_callback(f"Starting Ansible provisioning for {server_config['name']} ({server_config['ip_address']}) via direct Python API...\n")
        
        try:
            # Set up Ansible's internal components
            loader = DataLoader()
            loader.set_vault_password(vault_pass)
            
            # Create a temporary inventory for the single host
            inventory = InventoryManager(loader=loader, sources=f"{server_config['ip_address']},")
            
            # This is where your secrets are passed
            extra_vars = loader.load_from_file(os.path.join(self.controller.config_manager.sync_path, 'secrets', 'ansible.yml'))
            
            # Set up the VariableManager with the host variables and secrets
            variable_manager = VariableManager(loader=loader, inventory=inventory)
            
            # Add the specific host variables
            variable_manager.extra_vars = extra_vars
            variable_manager.options_vars = {
                'ansible_user': server_config['user'],
                'ansible_ssh_pass': server_config['password'] # Pass the password directly
            }
            
            # Set up the playbook executor
            pbex = PlaybookExecutor(
                playbooks=[self.playbook_path],
                inventory=inventory,
                variable_manager=variable_manager,
                loader=loader,
                passwords={'conn_pass': server_config['password'], 'become_pass': server_config['password']} # Pass the SSH password
            )
            
            # Attach the custom callback plugin
            results_callback = NydusNetCallback(log_callback)
            pbex._tqm._stdout_callback = results_callback
            
            return_code = pbex.run()
            
            if return_code == 0:
                log_callback("\n---\nProvisioning completed successfully!")
            else:
                log_callback(f"\n---\nProvisioning failed with exit code: {return_code}")

        except Exception as e:
            logging.error(f"An error occurred while running Ansible: {e}")
            log_callback(f"FATAL ERROR: {e}")
