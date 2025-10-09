import customtkinter as ctk
import logging
from views.dashboard_view import DashboardView
from views.settings_view import SettingsView
from views.history_view import HistoryView
from views.dialogs import UnlockDialog, ServerDialog, TunnelDialog, InviteDialog, ConfirmationDialog, RecoveryKeyDialog, ErrorDialog

from controllers.config_manager import ConfigManager
from controllers.tunnel_manager import TunnelManager
from controllers.syncthing_manager import SyncthingManager
from controllers.ansible_manager import AnsibleManager

class App(ctk.CTk):
    """
    The main application class. Acts as the central controller, managing the UI
    and coordinating all backend logic.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.title("NydusNet")
        self.geometry("900x650")
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.is_unlocked = False

        # --- Initialize Backend Controllers ---
        self.config_manager = ConfigManager(self)
        self.syncthing_manager = SyncthingManager(self)
        self.tunnel_manager = TunnelManager(self)
        self.ansible_manager = AnsibleManager(self)
        
        # --- Initialize UI Frames (Views) ---
        container = ctk.CTkFrame(self)
        container.pack(side="top", fill="both", expand=True)
        container.grid_row_configure(0, weight=1)
        container.grid_column_configure(0, weight=1)

        self.frames = {}
        for F in (DashboardView, SettingsView, HistoryView):
            page_name = F.__name__
            frame = F(parent=container, controller=self)
            self.frames[page_name] = frame
            frame.grid(row=0, column=0, sticky="nsew")

        # --- Application Startup ---
        # Start the unlock process immediately
        self.after(100, self.show_unlock_dialog)

    def show_unlock_dialog(self):
        """Shows the unlock dialog and waits for user input."""
        if self.is_unlocked: return
        
        is_first_run = not self.config_manager.is_configured()
        
        dialog = UnlockDialog(self, first_run=is_first_run, controller=self)
        password = dialog.get_input()
        
        if password is None: # User closed the dialog
            self.destroy()
            return
        
        if is_first_run:
            self.handle_first_run(password)
        else:
            self.attempt_unlock(password)

    def handle_first_run(self, password: str):
        """
        Handles the special logic for the very first run, including generating
        and displaying the recovery key.
        """
        logging.info("First-time setup: A new master password is being created.")
        
        if self.config_manager.unlock_with_password(password):
            recovery_key = self.config_manager.crypto_manager.generate_recovery_key()
            self.config_manager.save_recovery_key(recovery_key, password)
            RecoveryKeyDialog(self, recovery_key=recovery_key)
            
            logging.info("First-time setup complete. Starting backend services.")
            self.is_unlocked = True
            if not self.syncthing_manager.start():
                 ErrorDialog(self, message="Syncthing failed to start. Please check the logs.")
                 return # Don't proceed if core service fails
            self.show_frame("DashboardView")
        else:
            logging.warning("First-time password creation failed.")
            ErrorDialog(self, message="Failed to create password. Please try again.")
            self.show_unlock_dialog()

    def attempt_unlock(self, password: str):
        """
        Attempts to decrypt the configuration. If successful, starts backend services
        and shows the dashboard. If not, re-prompts for the password.
        """
        if self.config_manager.unlock_with_password(password):
            logging.info("Unlock successful. Starting backend services.")
            self.is_unlocked = True
            if not self.syncthing_manager.start():
                 ErrorDialog(self, message="Syncthing failed to start. Please check the logs.")
                 return
            self.show_frame("DashboardView")
        else:
            logging.warning("Unlock failed: incorrect master password.")
            ErrorDialog(self, message="Incorrect master password. Please try again.")
            self.show_unlock_dialog()

    def forgot_password(self):
        """
        Starts the password reset workflow.
        """
        logging.info("Starting password reset workflow.")
        
        # Step 1: Prompt the user to enter their recovery key.
        recovery_dialog = RecoveryKeyDialog(self, title="Password Reset", input_mode=True)
        recovery_key = recovery_dialog.get_input()
        if not recovery_key: return # User cancelled

        # Step 2: Prompt for a new password.
        new_password_dialog = UnlockDialog(self, first_run=True, title="Create New Master Password")
        new_password = new_password_dialog.get_input()
        if not new_password: return # User cancelled
        
        # Step 3: Call the config manager to perform the re-encryption.
        if self.config_manager.re_encrypt_with_new_password(old_key=recovery_key, new_password=new_password):
            logging.info("Password successfully reset. Attempting to unlock with the new password.")
            self.attempt_unlock(new_password)
        else:
            logging.error("Password reset failed. The recovery key was likely incorrect.")
            ErrorDialog(self, message="Password reset failed. The recovery key was incorrect.")
            self.show_unlock_dialog()

    def change_master_password(self):
        """
        Allows the user to change their master password.
        """
        logging.info("Starting master password change workflow.")

        old_password_dialog = UnlockDialog(self, title="Enter Old Master Password")
        old_password = old_password_dialog.get_input()
        if not old_password: return

        if self.config_manager.unlock_with_password(old_password):
            new_password_dialog = UnlockDialog(self, first_run=True, title="Enter New Master Password")
            new_password = new_password_dialog.get_input()
            if not new_password: return

            if self.config_manager.re_encrypt_with_new_password(old_key=old_password, new_password=new_password):
                ConfirmationDialog(self, message="Password successfully changed!")
            else:
                ErrorDialog(self, message="Failed to change password. The new password could not be applied.")
        else:
            ErrorDialog(self, message="Incorrect old password.")

    def view_recovery_key(self):
        """
        Retrieves and displays the recovery key to the user.
        """
        logging.info("Attempting to display recovery key.")
        recovery_key = self.config_manager.get_recovery_key()
        if recovery_key:
            RecoveryKeyDialog(self, recovery_key=recovery_key)
        else:
            ErrorDialog(self, message="Recovery key not found or could not be decrypted.")
        
    def show_frame(self, page_name: str):
        """Raises the given frame to the top so it's visible."""
        if not self.is_unlocked: return # Prevent showing frames before unlock
        
        logging.info(f"Switching to view: {page_name}")
        frame = self.frames[page_name]
        if hasattr(frame, 'enter') and callable(getattr(frame, 'enter')):
            frame.enter()
        frame.tkraise()

    def refresh_dashboard(self):
        """Safely triggers a refresh of the dashboard from any thread."""
        dashboard = self.frames.get("DashboardView")
        if dashboard and self.is_unlocked:
            self.after(0, dashboard.load_tunnels)

    def on_closing(self):
        """Handles the application shutdown sequence."""
        logging.info("Application closing. Shutting down services...")
        if self.is_unlocked:
            self.tunnel_manager.stop_all_tunnels()
            self.syncthing_manager.stop()
        self.destroy()

    # --- Controller Passthrough Methods ---
    # These are called by the Views and delegate work to the backend managers.

    # Config Manager Methods
    def get_tunnels(self): return self.config_manager.get_tunnels()
    def get_servers(self): return self.config_manager.get_servers()
    def get_clients(self): return self.config_manager.get_clients()
    def get_server_name(self, server_id): return self.config_manager.get_server_name(server_id)
    def get_automation_credentials(self): return self.config_manager.get_automation_credentials()

    def add_new_tunnel(self):
        dialog = TunnelDialog(self, controller=self, title="Add New Tunnel")
        data = dialog.get_input()
        if data:
            self.config_manager.add_object('tunnel', data)
            self.refresh_dashboard()

    def edit_tunnel(self, tunnel_id):
        tunnel_data = self.config_manager.get_object_by_id(tunnel_id)
        dialog = TunnelDialog(self, controller=self, title="Edit Tunnel", initial_data=tunnel_data)
        new_data = dialog.get_input()
        if new_data:
            self.config_manager.update_object(tunnel_id, new_data)
            self.refresh_dashboard()
            
    # Tunnel Manager Methods
    def start_tunnel(self, tunnel_id): 
        if not self.tunnel_manager.start_tunnel(tunnel_id):
            ErrorDialog(self, message="Failed to start tunnel. Check logs for details.")
        self.refresh_dashboard()
    def stop_tunnel(self, tunnel_id): 
        self.tunnel_manager.stop_tunnel(tunnel_id)
        self.refresh_dashboard()
    def start_all_tunnels(self): self.tunnel_manager.start_all_tunnels()
    def stop_all_tunnels(self): self.tunnel_manager.stop_all_tunnels()
    def get_tunnel_statuses(self): return self.tunnel_manager.get_tunnel_statuses()

    # Syncthing Manager Methods
    def add_new_device(self):
        invite_string = self.syncthing_manager.generate_invite()
        if invite_string:
            InviteDialog(self, invite_string=invite_string) # This dialog is view-only
        
    # Ansible Manager Methods
    def add_new_server(self):
        dialog = ServerDialog(self, title="Add & Provision New Server")
        server_info = dialog.get_input()
        if server_info:
            server_id = self.config_manager.add_object('server', server_info)
            
            log_window = ctk.CTkToplevel(self)
            log_window.title(f"Provisioning {server_info['name']}...")
            log_textbox = ctk.CTkTextbox(log_window, width=700, height=400)
            log_textbox.pack(fill="both", expand=True)
            
            def log_callback(message):
                log_textbox.insert("end", message + "\n")
                log_textbox.see("end")

                if message.startswith("ERROR:"):
                    ErrorDialog(self, message.replace("ERROR: ", ""))

            self.ansible_manager.provision_server(server_id, log_callback)

    # History Methods
    def get_history_file_index(self): return self.config_manager.get_history_file_index()
    def get_file_version_history(self, file_id): return self.config_manager.get_file_version_history(file_id)
    def get_file_content_at_version(self, file_id, timestamp): return self.config_manager.get_file_content_at_version(file_id, timestamp)
