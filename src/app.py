import customtkinter as ctk
import logging
import threading
import os
import socket
from PIL import Image
import pystray
from tkinter import filedialog
import time

# --- Import views ---
from views.dashboard_view import DashboardView
from views.servers_view import ServersView # <-- ADDED
from views.settings_view import SettingsView
from views.history_view import HistoryView
from views.debug_view import DebugView
# --- Import dialogs ---
from views.dialogs import (
    UnlockDialog, ServerDialog, TunnelDialog, InviteDialog,
    ConfirmationDialog, RecoveryKeyDialog, ErrorDialog, LoadingDialog, LogViewerDialog,
    ProvisionDialog, ProvisioningLogDialog
)
# --- Import controllers and utils ---
from controllers.config_manager import ConfigManager
from controllers.tunnel_manager import TunnelManager
from controllers.syncthing_manager import SyncthingManager
from controllers.server_provisioner import ServerProvisioner
from utils.crypto import CryptoManager

class App(ctk.CTk):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.title("NydusNet")
        # --- SET ICON BITMAP ---
        try:
            src_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(src_dir)
            base_path = getattr(os, '_MEIPASS', project_root)
            icon_path = os.path.join(base_path, "resources", "images", "nydusnet.ico")
            if os.path.exists(icon_path):
                 self.iconbitmap(icon_path)
                 logging.info(f"Application icon set from: {icon_path}")
            else:
                 logging.warning(f"Application icon not found at {icon_path}")
        except Exception as e:
            logging.warning(f"Failed to set application icon: {e}")
        # --- END ICON BITMAP ---

        self.geometry("900x550")
        # --- Allow resizing and set minimum size ---
        self.resizable(True, True)
        self.minsize(700, 500) # Adjusted minimum size

        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        # --- Handle minimize differently ---
        self.bind("<Unmap>", self._on_minimize) # Detect when minimized
        self.minimized_to_tray = False # Flag to track state

        self.is_unlocked = False
        self.is_shutting_down = False
        self.syncthing_id_ready = threading.Event()

        # --- Load all images first ---
        self.images = self._load_images()

        # --- Config managers ---
        self.config_manager = ConfigManager(self)
        self.syncthing_manager = SyncthingManager(self)
        self.tunnel_manager = TunnelManager(self)
        self.crypto_manager = CryptoManager()

        # --- Configure root grid layout (1 row, 2 columns) ---
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1) # Content area expands

        # --- Create sidebar navigation frame ---
        self.sidebar_frame = self._create_sidebar()
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")

        # --- Create content frame (replaces old 'container') ---
        self.content_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.content_frame.grid(row=0, column=1, sticky="nsew")
        self.content_frame.grid_rowconfigure(0, weight=1)
        self.content_frame.grid_columnconfigure(0, weight=1)

        # --- Add Sidebar Toggle Button ---
        # Place button INSIDE content_frame for relative positioning
        self.sidebar_toggle_button = ctk.CTkButton(self.content_frame, text="☰", width=30, height=30,
                                                   corner_radius=5, fg_color="transparent",
                                                   hover_color=("gray70", "gray30"),
                                                   command=self._toggle_sidebar)
        # Initial position will be set by _update_toggle_button_position

        # --- Initialize all view frames ---
        self.frames = {}
        # --- ADD ServersView to this list ---
        for F in (DashboardView, ServersView, SettingsView, HistoryView, DebugView):
            page_name = F.__name__
            frame = F(parent=self.content_frame, controller=self)
            self.frames[page_name] = frame
            # Grid views within the content_frame
            frame.grid(row=0, column=0, padx=0, pady=0, sticky="nsew")

        # --- Set initial sidebar state and button position AFTER sidebar exists ---
        self._update_toggle_button_position() # Call helper to set correct initial pos

        self.withdraw() # Start hidden
        self.after(100, self.show_unlock_dialog)
        self.tray_icon = None

    def _load_images(self) -> dict:
        """Loads all images used by the app into a dictionary."""
        image_dict = {}
        try:
            src_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(src_dir)
            base_path = getattr(os, '_MEIPASS', project_root)
            image_dir = os.path.join(base_path, "resources", "images")
            logging.info(f"Loading images from: {image_dir}")

            def load_img(key, filename, size=(20, 20)):
                try:
                    path = os.path.join(image_dir, filename)
                    if not os.path.exists(path):
                        raise FileNotFoundError(f"Image file not found: {path}")
                    image_dict[key] = ctk.CTkImage(Image.open(path), size=size)
                    logging.debug(f"Loaded image '{key}' from {filename}")
                except Exception as e:
                    logging.warning(f"Failed to load image '{key}' from {filename}. Error: {e}")
                    # Store a placeholder image or None if preferred
                    image_dict[key] = ctk.CTkImage(Image.new('RGB', size, color='red'), size=size)

            # Load images for navigation, actions, and dialogs
            load_img("logo", "nydusnet_logo.png", (26, 26))
            load_img("dashboard", "dashboard.png") # Used for 'Tunnels' button
            load_img("settings", "settings.png")
            load_img("history", "history.png")
            load_img("debug", "debug.png")
            load_img("start", "start.png")
            load_img("stop", "stop.png")
            load_img("edit", "edit.png")
            load_img("logs", "logs.png")
            load_img("delete", "delete.png")
            load_img("add", "add.png")
            load_img("start_all", "start_all.png")
            load_img("stop_all", "stop_all.png")
            load_img("add_device", "add_device.png")
            load_img("setup", "setup.png") # Used for 'Servers' button now too
            load_img("eye-show", "eye-show.png")
            load_img("eye-hide", "eye-hide.png")
            load_img("bg_gradient", "bg_gradient.jpg", (400, 300))
            # load_img("server", "server.png") # Add if you create a specific server icon

        except Exception as e:
            logging.error(f"Critical error during image loading setup: {e}", exc_info=True)
            # Return potentially partially filled dict or empty dict on major failure
        return image_dict


    def _toggle_sidebar(self):
        """Shows or hides the sidebar frame and adjusts the toggle button position."""
        if self.sidebar_frame.winfo_ismapped():
            # Hide sidebar
            self.sidebar_frame.grid_forget()
            self.sidebar_toggle_button.configure(text="☰") # Or change to ">" icon if you add one
            logging.debug("Sidebar hidden.")
        else:
            # Show sidebar
            self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
            self.sidebar_toggle_button.configure(text="☰") # Or change back to "<" icon
            logging.debug("Sidebar shown.")
        # Update button position after showing/hiding, slight delay helps ensure frame width is updated
        self.after(20, self._update_toggle_button_position)


    def _update_toggle_button_position(self):
        """Places the sidebar toggle button correctly based on sidebar visibility."""
        if not hasattr(self, 'sidebar_toggle_button') or not self.sidebar_toggle_button.winfo_exists():
            return # Skip if button doesn't exist yet

        if self.sidebar_frame.winfo_ismapped():
             # Use current width if visible
             sidebar_width = self.sidebar_frame.winfo_width()
             target_x = sidebar_width + 10 if sidebar_width > 0 else 160 + 10 # Fallback position if width is 0 initially
             self.sidebar_toggle_button.place(x=target_x, y=10)
             # logging.debug(f"Positioning toggle next to sidebar at x={target_x}")
        else:
            # Move toggle button to the far left edge when hidden
            self.sidebar_toggle_button.place(x=10, y=10)
            # logging.debug("Positioning toggle at far left (x=10)")


    def _create_sidebar(self) -> ctk.CTkFrame:
        """Creates and configures the sidebar navigation frame."""
        frame = ctk.CTkFrame(self, width=160, corner_radius=0) # Increased width
        frame.grid_propagate(False) # Prevent frame from shrinking
        frame.grid_rowconfigure(6, weight=1) # Push empty space below buttons

        logo_label = ctk.CTkLabel(frame, text=" NydusNet", image=self.images.get("logo"),
                                     compound="left", font=ctk.CTkFont(size=16, weight="bold"))
        logo_label.grid(row=0, column=0, padx=15, pady=20, sticky="ew")

        # --- Navigation Buttons ---
        self.dashboard_button = ctk.CTkButton(frame, corner_radius=0, height=40, border_spacing=10,
                                                text="Tunnels", fg_color="transparent", # RENAMED
                                                text_color=("gray10", "gray90"),
                                                hover_color=("gray70", "gray30"),
                                                image=self.images.get("dashboard"), anchor="w",
                                                command=lambda: self.show_frame("DashboardView"))
        self.dashboard_button.grid(row=1, column=0, sticky="ew")

        self.servers_button = ctk.CTkButton(frame, corner_radius=0, height=40, border_spacing=10,
                                               text="Servers", fg_color="transparent", # NEW
                                               text_color=("gray10", "gray90"),
                                               hover_color=("gray70", "gray30"),
                                               image=self.images.get("setup"), anchor="w", # Using 'setup' icon
                                               command=lambda: self.show_frame("ServersView"))
        self.servers_button.grid(row=2, column=0, sticky="ew")

        self.settings_button = ctk.CTkButton(frame, corner_radius=0, height=40, border_spacing=10,
                                               text="Settings", fg_color="transparent",
                                               text_color=("gray10", "gray90"),
                                               hover_color=("gray70", "gray30"),
                                               image=self.images.get("settings"), anchor="w",
                                               command=lambda: self.show_frame("SettingsView"))
        self.settings_button.grid(row=3, column=0, sticky="ew") # New row

        self.history_button = ctk.CTkButton(frame, corner_radius=0, height=40, border_spacing=10,
                                              text="History", fg_color="transparent",
                                              text_color=("gray10", "gray90"),
                                              hover_color=("gray70", "gray30"),
                                              image=self.images.get("history"), anchor="w",
                                              command=lambda: self.show_frame("HistoryView"))
        self.history_button.grid(row=4, column=0, sticky="ew") # New row

        self.debug_button = ctk.CTkButton(frame, corner_radius=0, height=40, border_spacing=10,
                                            text="Debug", fg_color="transparent",
                                            text_color=("gray10", "gray90"),
                                            hover_color=("gray70", "gray30"),
                                            image=self.images.get("debug"), anchor="w",
                                            command=lambda: self.show_frame("DebugView"))
        self.debug_button.grid(row=5, column=0, sticky="ew") # New row

        # --- Appearance Mode Menu REMOVED from sidebar ---

        return frame

    def on_syncthing_id_ready(self):
        """Callback from SyncthingManager when the device ID is available."""
        logging.info("Syncthing ID is ready. Refreshing relevant views.")
        self.syncthing_id_ready.set()
        # Refresh settings view if it's currently visible
        if "SettingsView" in self.frames and self.frames["SettingsView"].winfo_viewable():
            self.after(0, self.frames["SettingsView"].enter)
        # Always refresh dashboard after ID is ready
        self.after(0, self.refresh_dashboard)


    def _setup_tray_icon(self):
        try:
            src_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(src_dir)
            base_path = getattr(os, '_MEIPASS', project_root)
            icon_path = os.path.join(base_path, "resources", "images", "nydusnet.ico")
            if not os.path.exists(icon_path):
                raise FileNotFoundError(f"Tray icon not found: {icon_path}")
            icon_image = Image.open(icon_path)
            logging.info(f"Tray icon loaded from: {icon_path}")
        except Exception as e:
            logging.warning(f"System tray icon error ({e}), using a placeholder.")
            icon_image = Image.new('RGB', (64, 64), color='blue') # Placeholder

        menu = (
            pystray.MenuItem('Show', self.show_window, default=True),
            pystray.MenuItem('Quit', self.quit_application)
        )
        self.tray_icon = pystray.Icon("NydusNet", icon_image, "NydusNet", menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def show_window(self):
        """Shows the main window and resets the minimized flag."""
        self.minimized_to_tray = False # Reset flag
        try:
            if not self.winfo_exists(): return # Prevent errors if called during shutdown
            self.deiconify()
            self.lift()
            self.focus_force()
            self.attributes('-topmost', True) # Bring to front
            self.after(100, lambda: self.attributes('-topmost', False) if self.winfo_exists() else None) # Release topmost safely
            self._update_toggle_button_position() # Ensure button is correctly placed
        except Exception as e:
            logging.error(f"Error in show_window: {e}")


    def quit_application(self):
        logging.info("Quit command received.")
        # Stop tray icon first if it exists and is running
        if hasattr(self, 'tray_icon') and self.tray_icon and getattr(self.tray_icon, 'HAS_NOTIFICATION', False): # pystray check
             try:
                 self.tray_icon.stop()
                 logging.info("Tray icon stopped.")
             except Exception as e:
                 logging.warning(f"Error stopping tray icon: {e}")
        self.tray_icon = None # Clear reference
        self.on_closing(force_quit=True) # Trigger shutdown


    def _on_minimize(self, event=None):
        """Handles minimizing the window to the system tray."""
        # Check if the state change is actually to 'iconic' (minimized)
        try:
            # Check if window exists before getting state
            if self.winfo_exists() and self.state() == 'iconic' and not self.minimized_to_tray:
                logging.info("Minimizing to system tray via minimize button.")
                self.minimized_to_tray = True
                self.withdraw() # Hide the window
        except Exception as e:
            # Handle cases where state() might fail if window is closing
            logging.debug(f"Ignoring minimize event during potential close: {e}")


    def on_closing(self, force_quit=False):
        """Handles closing the window or quitting the application."""
        if force_quit:
            if not self.is_shutting_down:
                self.is_shutting_down = True
                logging.info("Application closing initiated (force_quit=True).")
                if self.is_unlocked:
                    logging.info("Stopping background services...")
                    # Gracefully stop background services
                    self.tunnel_manager.stop()
                    self.syncthing_manager.stop()
                # Stop tray icon if running
                if hasattr(self, 'tray_icon') and self.tray_icon and getattr(self.tray_icon, 'HAS_NOTIFICATION', False):
                    try:
                        self.tray_icon.stop()
                        logging.info("Tray icon stopped during quit.")
                    except Exception as e:
                        logging.warning(f"Error stopping tray icon during quit: {e}")
                self.tray_icon = None # Clear ref
                logging.info("Scheduling main window destruction.")
                self.after(200, self.destroy) # Schedule final destruction
        else:
            # This is triggered by the 'X' button
            logging.info("Hiding to system tray via close button.")
            self.minimized_to_tray = True # Set flag to indicate hidden state
            self.withdraw() # Hide the window

    def show_unlock_dialog(self):
        if self.is_unlocked: return
        is_first_run = not self.config_manager.is_configured()
        dialog = UnlockDialog(self, first_run=is_first_run, controller=self)

        # --- Bring to foreground and focus (More Aggressive) ---
        dialog.attributes('-topmost', True) # Force it on top initially
        dialog.lift()
        dialog.focus_force()
        # Schedule turning off topmost after a brief moment
        # Check if dialog still exists before changing attributes
        self.after(100, lambda: dialog.attributes('-topmost', False) if dialog.winfo_exists() else None)
        # Ensure focus goes to entry *after* the dialog itself has focus
        self.after(50, lambda: dialog.entry1.focus_set() if dialog.winfo_exists() and hasattr(dialog, 'entry1') else None)
        # --- End ---

        password = dialog.get_input()

        if password is None: # User closed the dialog
            logging.info("Unlock dialog closed by user. Exiting.")
            # Check if shutting down already, otherwise initiate clean quit
            if not self.is_shutting_down:
                 self.quit_application()
            return

        if is_first_run:
            self.handle_first_run(password)
        else:
            self.attempt_unlock(password)

    def handle_first_run(self, password: str):
        unlock_successful, recovery_key = self.config_manager.unlock_with_password(password)
        if unlock_successful:
            self.is_unlocked = True
            logging.info("First run: Generating and saving SSH key pair for automation.")
            try:
                priv_path, pub_path = self.crypto_manager.generate_ssh_key_pair()
                self.save_or_update_automation_credentials(priv_path, pub_path)
            except Exception as e:
                logging.error(f"Failed to generate/save SSH keys on first run: {e}", exc_info=True)
                self.show_error("Error generating initial SSH keys. Check logs.")
                # Continue, but SSH automation might fail later

            # --- Wait for Recovery Key Dialog ---
            key_dialog = RecoveryKeyDialog(self, recovery_key=recovery_key)
            key_dialog.wait_window() # Pause execution until dialog is closed
            # --- End Wait ---

            # Setup tray icon *before* starting backend services potentially
            if not self.tray_icon: self._setup_tray_icon()
            self._start_backend_services_threaded() # Start services *after* key dialog
        else:
            self.show_error("Failed to create password. Please try again.")
            self.after(100, self.show_unlock_dialog) # Show unlock again after error dialog

    def attempt_unlock(self, password: str):
        unlock_successful, _ = self.config_manager.unlock_with_password(password)
        if unlock_successful:
            self.is_unlocked = True
            if not self.tray_icon: self._setup_tray_icon()
            self._start_backend_services_threaded()
        else:
            self.show_error("Incorrect master password. Please try again.")
            self.after(100, self.show_unlock_dialog) # Show unlock again after error

    def _start_backend_services_threaded(self):
        loading_dialog = LoadingDialog(self)
        self.update_idletasks() # Ensure dialog appears

        def service_starter():
            start_success = False
            try:
                start_success = self.syncthing_manager.start()
            except Exception as e:
                logging.error(f"Exception during Syncthing start: {e}", exc_info=True)
                # Safely destroy dialog from main thread
                if loading_dialog.winfo_exists():
                    self.after(0, loading_dialog.destroy)
                self.after(0, lambda: self.show_error(f"Syncthing failed to start critical service. Check logs.\nError: {e}"))
                self.after(100, self.quit_application) # Quit if backend fails crucially
                return

            if start_success:
                logging.info("Syncthing started successfully.")
                if loading_dialog.winfo_exists():
                    self.after(0, loading_dialog.destroy)
                # Show main window sequence
                self.after(10, self.show_window)
                self.after(20, lambda: self.show_frame("DashboardView")) # Show Tunnels view
            else:
                 logging.error("Syncthing manager returned False on start.")
                 if loading_dialog.winfo_exists():
                    self.after(0, loading_dialog.destroy)
                 self.after(0, lambda: self.show_error("Syncthing failed to start. Check logs for details."))
                 self.after(100, self.quit_application)

        threading.Thread(target=service_starter, daemon=True).start()


    def forgot_password(self):
        logging.info("Starting password reset workflow.")
        recovery_dialog = RecoveryKeyDialog(self, title="Password Reset", input_mode=True)
        recovery_key = recovery_dialog.get_input()
        if not recovery_key: return # User cancelled recovery key input

        # Ask for new password only if recovery key was entered
        new_password_dialog = UnlockDialog(self, first_run=True, title="Create New Master Password", controller=self)
        new_password = new_password_dialog.get_input()
        if not new_password: return # User cancelled new password creation

        # Attempt re-encryption
        if self.config_manager.re_encrypt_with_new_password(old_key=recovery_key, new_password=new_password):
            logging.info("Password successfully reset using recovery key.")
            # Show success message before attempting unlock
            conf_dialog = ConfirmationDialog(self, title="Success", message="Password successfully reset!")
            conf_dialog.wait_window()
            self.attempt_unlock(new_password) # Try unlocking with the new password
        else:
            self.show_error("Password reset failed. The recovery key was likely incorrect.")
            self.after(100, self.show_unlock_dialog) # Go back to login after error


    def change_master_password(self):
        logging.info("Starting master password change workflow.")
        old_password_dialog = UnlockDialog(self, title="Enter Old Master Password", controller=self)
        old_password = old_password_dialog.get_input()
        if not old_password: return # User cancelled

        try:
            # Verify old password *before* asking for new one
            if self.config_manager.verify_password(old_password):
                new_password_dialog = UnlockDialog(self, first_run=True, title="Enter New Master Password", controller=self)
                new_password = new_password_dialog.get_input()
                if not new_password: return # User cancelled new password

                # Attempt re-encryption
                if self.config_manager.re_encrypt_with_new_password(old_key=old_password, new_password=new_password):
                    conf_dialog = ConfirmationDialog(self, title="Success", message="Master password successfully changed!")
                    conf_dialog.wait_window() # Show confirmation
                else:
                    self.show_error("Failed to change password during re-encryption. Check logs.")
            else:
                self.show_error("Incorrect old password.")
        except Exception as e:
            logging.error(f"Error during password change: {e}", exc_info=True)
            self.show_error(f"An unexpected error occurred during password change.")


    def view_recovery_key(self):
        logging.info("Attempting to display recovery key.")
        # Ask for current password to authorize viewing the key
        password_dialog = UnlockDialog(self, title="Enter Master Password to View Key", controller=self)
        password = password_dialog.get_input()
        if not password: return # User cancelled

        if self.config_manager.verify_password(password):
            recovery_key = self.config_manager.get_recovery_key(password) # Pass password to decrypt
            if recovery_key:
                RecoveryKeyDialog(self, recovery_key=recovery_key, input_mode=False)
            else:
                # This might happen if config is corrupted or password check somehow passed incorrectly
                self.show_error("Recovery key could not be retrieved even with the correct password. Config might be inconsistent.")
        else:
            self.show_error("Incorrect master password.")


    def show_frame(self, page_name: str):
        """Shows the selected frame and updates the sidebar button states."""
        if not self.is_unlocked:
             logging.warning(f"Attempted to show frame '{page_name}' while locked.")
             return
        if page_name not in self.frames:
            logging.error(f"Attempted to show unknown frame: {page_name}")
            return

        logging.info(f"Switching to view: {page_name}")

        selected_color = ("gray75", "gray25") # Highlight color

        # Update button colors
        self.dashboard_button.configure(fg_color=selected_color if page_name == "DashboardView" else "transparent")
        self.servers_button.configure(fg_color=selected_color if page_name == "ServersView" else "transparent")
        self.settings_button.configure(fg_color=selected_color if page_name == "SettingsView" else "transparent")
        self.history_button.configure(fg_color=selected_color if page_name == "HistoryView" else "transparent")
        self.debug_button.configure(fg_color=selected_color if page_name == "DebugView" else "transparent")

        frame = self.frames[page_name]

        # Call the frame's enter() method using after(0)
        if hasattr(frame, 'enter') and callable(getattr(frame, 'enter')):
            self.after(0, frame.enter)

        frame.tkraise()
        # Update toggle button position after view might have changed layout
        self.after(10, self._update_toggle_button_position)


    def refresh_dashboard(self):
        """Safely schedules a refresh of the dashboard (Tunnels) view if visible."""
        if self.is_shutting_down: return
        dashboard = self.frames.get("DashboardView")
        if dashboard and self.is_unlocked and dashboard.winfo_viewable():
            logging.debug("Scheduling Tunnels view refresh.")
            self.after(0, dashboard.load_tunnels)
        else:
             logging.debug("Skipping Tunnels view refresh (not visible or not ready).")


    def show_error(self, message: str):
        """Displays an error dialog."""
        logging.error(f"Displaying error: {message}")
        ErrorDialog(self, message=message)


    def set_appearance_mode(self, mode: str):
        """Sets the application's appearance mode."""
        logging.info(f"Setting appearance mode to: {mode}")
        ctk.set_appearance_mode(mode)
        # Update toggle button position in case appearance change affects sidebar width
        self.after(10, self._update_toggle_button_position)


    def provision_server(self, server_id):
        server = self.get_object_by_id(server_id)
        if not server:
            self.show_error(f"Server not found (ID: {server_id})."); return

        dialog = ProvisionDialog(self, server.get('name', 'Unknown'), server.get('ip_address', 'No IP'))
        creds = dialog.get_input()
        if not creds: return # User cancelled

        creds_obj = self.get_automation_credentials()
        if not creds_obj or not creds_obj.get('ssh_public_key_path'):
            self.show_error("Public SSH key path not configured. Please set it in Settings > SSH Keys.")
            return

        pub_key_path = creds_obj['ssh_public_key_path']
        try:
            if not os.path.exists(pub_key_path):
                 raise FileNotFoundError(f"Public key file not found at: {pub_key_path}")
            with open(pub_key_path, 'r') as f:
                pub_key_string = f.read().strip()
            if not pub_key_string:
                 raise ValueError("Public key file is empty.")
        except FileNotFoundError as e:
            self.show_error(str(e))
            return
        except ValueError as e:
             self.show_error(str(e))
             return
        except Exception as e:
             logging.error(f"Error reading public key {pub_key_path}: {e}", exc_info=True)
             self.show_error(f"Error reading public key. Check file permissions and content.")
             return

        provisioner = ServerProvisioner(server['ip_address'], creds['user'], creds['password'], pub_key_string)
        log_dialog = ProvisioningLogDialog(self, server['name'])

        def run_in_thread():
            success, final_log = provisioner.run()
            # Safely update GUI from the main thread using 'after'
            # Check if dialog still exists before updating
            self.after(0, lambda: log_dialog.complete(success) if log_dialog.winfo_exists() else None)
            if success:
                logging.info(f"Server {server_id} provisioned successfully.")
                # Fetch latest server data in case it was edited elsewhere during provisioning
                current_server_data = self.get_object_by_id(server_id)
                if current_server_data:
                    updated_server = current_server_data.copy()
                    updated_server['is_provisioned'] = True
                    if not updated_server.get('tunnel_user'): # Set default tunnel user if needed
                        updated_server['tunnel_user'] = "tunnel"
                    self.config_manager.update_object(server_id, updated_server)
                    # --- Refresh ServersView ---
                    if "ServersView" in self.frames:
                        self.after(10, self.frames["ServersView"].enter)
                else:
                    logging.warning(f"Server {server_id} disappeared during provisioning.")
            else:
                 logging.error(f"Server provisioning failed for {server_id}.")

        def log_monitor():
            while provision_thread.is_alive():
                # Check if dialog exists before scheduling update
                if log_dialog.winfo_exists():
                    self.after(50, lambda: log_dialog.update_log(provisioner.log_output) if log_dialog.winfo_exists() else None)
                time.sleep(0.2) # Check periodically
            # Final update after thread finishes, check dialog exists
            if log_dialog.winfo_exists():
                self.after(50, lambda: log_dialog.update_log(provisioner.log_output) if log_dialog.winfo_exists() else None)

        # Start threads
        provision_thread = threading.Thread(target=run_in_thread, daemon=True)
        provision_thread.start()
        monitor_thread = threading.Thread(target=log_monitor, daemon=True)
        monitor_thread.start()

    # --- Passthrough Methods ---
    def get_all_objects_for_debug(self): return self.config_manager.get_all_objects_for_debug()
    def get_object_by_id(self, obj_id: str): return self.config_manager.get_object_by_id(obj_id)
    def get_tunnels(self): return self.config_manager.get_tunnels()
    def get_servers(self): return self.config_manager.get_servers()
    def get_clients(self): return self.config_manager.get_clients()
    def get_server_name(self, server_id): return self.config_manager.get_server_name(server_id)
    def get_client_name(self, client_id): return self.config_manager.get_client_name(client_id)
    def get_automation_credentials(self): return self.config_manager.get_automation_credentials()

    def get_my_device_name(self):
        try: return socket.gethostname()
        except Exception: return "Unknown Device"

    def get_my_device_id(self):
        if not self.syncthing_id_ready.is_set():
             logging.debug("Waiting briefly for Syncthing ID...")
             self.syncthing_id_ready.wait(timeout=5.0) # Wait up to 5 seconds
        device_id = self.syncthing_manager.my_device_id
        # logging.debug(f"get_my_device_id returning: {device_id}")
        return device_id

    def get_clients_for_dropdown(self):
        clients = self.get_clients()
        my_id = self.get_my_device_id() # Make sure this is called
        my_name = f"{self.get_my_device_name()} (This Device)"
        # Include 'This Device' only if the ID is known
        client_map = {my_name: my_id} if my_id else {}
        for client in clients:
            client_syncthing_id = client.get('syncthing_id')
            # Exclude this device even if ID matches (already added or shouldn't be selectable)
            if client_syncthing_id and client_syncthing_id != my_id:
                name = client.get('name', client_syncthing_id[:12]) # Fallback name
                client_map[name] = client_syncthing_id
        # Return map and sorted list of names
        return client_map, sorted(list(client_map.keys()))

    def save_or_update_automation_credentials(self, priv, pub):
        self.config_manager.save_or_update_automation_credentials(priv, pub)

    def browse_for_file(self, title="Select a file"):
        # Make the file dialog appear on top of the current window
        return filedialog.askopenfilename(title=title, parent=self)

    def add_new_tunnel(self):
        # Check for provisioned servers before opening dialog
        provisioned_servers = [s for s in self.get_servers() if s.get('is_provisioned')]
        if not provisioned_servers:
            self.show_error("You must register and successfully set up (provision) a Server before creating a tunnel.")
            # Optionally switch to Servers view
            # self.show_frame("ServersView")
            return

        dialog = TunnelDialog(self, controller=self, title="Add New Tunnel")
        data = dialog.get_input()
        if data:
            new_id = self.config_manager.add_object('tunnel', data)
            if new_id: # Check if add was successful
                logging.info(f"Added new tunnel: {new_id}")
                # Start if enabled and assigned to this device
                if data.get('enabled') and data.get('assigned_client_id') == self.get_my_device_id():
                    self.start_tunnel(new_id)
                self.refresh_dashboard() # Refresh Tunnels view
            else:
                logging.error("Failed to add new tunnel object.")
                self.show_error("Failed to save the new tunnel.")


    def edit_tunnel(self, tunnel_id):
        tunnel_data = self.get_object_by_id(tunnel_id)
        if not tunnel_data:
             self.show_error(f"Tunnel with ID {tunnel_id} not found for editing.")
             return
        dialog = TunnelDialog(self, controller=self, title="Edit Tunnel", initial_data=tunnel_data)
        new_data = dialog.get_input()
        if new_data:
             updated = self.config_manager.update_object(tunnel_id, new_data)
             if updated:
                  logging.info(f"Updated tunnel: {tunnel_id}")
                  # Check if the tunnel needs starting/stopping based on changes
                  was_enabled = tunnel_data.get('enabled', False)
                  now_enabled = new_data.get('enabled', False)
                  current_my_id = self.get_my_device_id() # Get potentially updated ID
                  was_mine = tunnel_data.get('assigned_client_id') == current_my_id
                  now_mine = new_data.get('assigned_client_id') == current_my_id

                  # If it's now managed by me and enabled, but wasn't before (or wasn't mine)
                  if now_mine and now_enabled and (not was_enabled or not was_mine):
                      self.start_tunnel(tunnel_id)
                  # If it's no longer managed by me, or no longer enabled, but was running under my management
                  elif (not now_mine or not now_enabled) and was_mine and was_enabled:
                       self.stop_tunnel(tunnel_id)

                  self.refresh_dashboard()
             else:
                  logging.error(f"Failed to update tunnel {tunnel_id}")
                  self.show_error("Failed to save tunnel updates.")


    def delete_tunnel(self, tunnel_id):
        tunnel = self.get_object_by_id(tunnel_id)
        if not tunnel:
            logging.warning(f"Attempted to delete non-existent tunnel: {tunnel_id}")
            self.refresh_dashboard() # Refresh list in case it was already deleted elsewhere
            return
        hostname = tunnel.get('hostname', tunnel_id[:8])
        dialog = ConfirmationDialog(self, message=f"Are you sure you want to delete the tunnel '{hostname}'?")
        if dialog.get_input():
             logging.info(f"Deleting tunnel: {tunnel_id}")
             self.stop_tunnel(tunnel_id) # Ensure it's stopped first
             deleted = self.config_manager.delete_object(tunnel_id)
             if deleted:
                 self.refresh_dashboard()
             else:
                  logging.error(f"Failed to delete tunnel {tunnel_id} from config.")
                  self.show_error("Failed to delete the tunnel.")


    def view_tunnel_log(self, tunnel_id: str):
        logs = self.tunnel_manager.get_tunnel_log(tunnel_id)
        tunnel = self.get_object_by_id(tunnel_id)
        title = f"Logs for {tunnel.get('hostname', tunnel_id[:8])}" if tunnel else f"Logs for {tunnel_id[:8]}"
        LogViewerDialog(self, log_content=logs or "No logs available for this tunnel yet.", title=title)


    def start_tunnel(self, tunnel_id: str):
        logging.info(f"Attempting to start tunnel: {tunnel_id}")
        success, message = self.tunnel_manager.start_tunnel(tunnel_id)
        if not success:
             self.show_error(message or f"Failed to start tunnel {tunnel_id}. Check logs.")
        # Refresh needed regardless of success to show 'connecting' or 'error' state
        self.after(100, self.refresh_dashboard) # Short delay


    def stop_tunnel(self, tunnel_id: str):
        logging.info(f"Stopping tunnel: {tunnel_id}")
        self.tunnel_manager.stop_tunnel(tunnel_id)
        self.after(100, self.refresh_dashboard) # Short delay


    def start_all_tunnels(self):
         logging.info("Starting all enabled tunnels assigned to this device.")
         self.tunnel_manager.start_all_tunnels()
         self.after(100, self.refresh_dashboard)


    def stop_all_tunnels(self):
         logging.info("Stopping all tunnels currently managed by this device.")
         self.tunnel_manager.stop_all_tunnels()
         self.after(100, self.refresh_dashboard)


    def get_tunnel_statuses(self):
         return self.tunnel_manager.get_tunnel_statuses()


    def add_new_device(self):
        my_id = self.get_my_device_id() # Ensure ID is retrieved
        if not my_id:
            self.show_error("Syncthing is still initializing. Please wait a moment and try again.")
            return
        invite_string = self.syncthing_manager.generate_invite()
        if invite_string:
             InviteDialog(self, invite_string=invite_string)
        else:
             self.show_error("Failed to generate device invite string. Check Syncthing status and logs.")


    def add_new_server(self):
        dialog = ServerDialog(self, title="Register New Server")
        server_info = dialog.get_input()
        if server_info:
            new_id = self.config_manager.add_object('server', server_info)
            if new_id:
                logging.info(f"Added new server: {new_id}")
                if "ServersView" in self.frames:
                     self.frames["ServersView"].enter() # Refresh list
            else:
                 logging.error("Failed to add new server object.")
                 self.show_error("Failed to save the new server.")


    def edit_server(self, server_id):
        server_data = self.get_object_by_id(server_id)
        if not server_data:
            self.show_error(f"Server with ID {server_id} not found for editing.")
            return
        dialog = ServerDialog(self, title="Edit Server", initial_data=server_data)
        new_data = dialog.get_input()
        if new_data:
             updated = self.config_manager.update_object(server_id, new_data)
             if updated:
                 logging.info(f"Updated server: {server_id}")
                 if "ServersView" in self.frames:
                      self.frames["ServersView"].enter() # Refresh list
                 # Also refresh dashboard in case server name change affects tunnel display
                 self.refresh_dashboard()
             else:
                  logging.error(f"Failed to update server {server_id}.")
                  self.show_error("Failed to save server updates.")


    def delete_server(self, server_id):
        server = self.get_object_by_id(server_id)
        if not server:
             logging.warning(f"Attempted to delete non-existent server: {server_id}")
             # Refresh list in case it was deleted elsewhere
             if "ServersView" in self.frames: self.frames["ServersView"].enter()
             return
        server_name = server.get('name', server_id[:8])

        # Check if any tunnels depend on this server BEFORE confirmation
        dependent_tunnels = [t for t in self.get_tunnels() if t.get('server_id') == server_id]
        if dependent_tunnels:
            tunnel_names = "\n - ".join([t.get('hostname', t['id'][:8]) for t in dependent_tunnels])
            self.show_error(f"Cannot delete server '{server_name}'.\nIt is used by the following tunnels:\n - {tunnel_names}\n\nPlease edit or delete these tunnels first.")
            return

        # Confirmation dialog
        dialog = ConfirmationDialog(self, message=f"Are you sure you want to delete the server '{server_name}'?")
        if dialog.get_input():
            logging.info(f"Deleting server: {server_id}")
            deleted = self.config_manager.delete_object(server_id)
            if deleted:
                if "ServersView" in self.frames:
                     self.frames["ServersView"].enter() # Refresh list
            else:
                 logging.error(f"Failed to delete server {server_id} from config.")
                 self.show_error("Failed to delete the server.")


    def remove_client(self, client_id):
        my_id = self.get_my_device_id()
        if client_id == my_id:
            self.show_error("Cannot remove this device from itself.")
            return

        # Find client name for confirmation message
        client_name = self.get_client_name(client_id)
        if not client_name: # Fallback if name not found in config (e.g., partially added device)
            try:
                # Ask Syncthing for its known name for this ID
                 st_devices = self.syncthing_manager.get_devices()
                 client_name = next((d['name'] for d in st_devices if d.get('deviceID') == client_id), client_id[:12])
            except Exception:
                 client_name = client_id[:12] # Fallback if Syncthing fails

        dialog = ConfirmationDialog(self, message=f"Remove device '{client_name}' ({client_id[:7]}...)?")
        if dialog.get_input():
            logging.info(f"Removing client: {client_id}")
            # Check for assigned tunnels BEFORE removing from Syncthing/Config
            assigned_tunnels = [t for t in self.get_tunnels() if t.get('assigned_client_id') == client_id]
            if assigned_tunnels:
                tunnel_names = "\n - ".join([t.get('hostname', t['id'][:8]) for t in assigned_tunnels])
                reassign_dialog = ConfirmationDialog(self, title="Reassign Tunnels?",
                                                      message=f"Device '{client_name}' manages these tunnels:\n - {tunnel_names}\n\nReassign them to THIS device ('{self.get_my_device_name()}') before removing '{client_name}'?")
                reassign = reassign_dialog.get_input()
                if reassign is None: return # User cancelled the reassign dialog

                if reassign:
                    if not my_id:
                         self.show_error("Cannot reassign tunnels, this device's ID is not yet known. Wait for Syncthing.")
                         return
                    logging.info(f"Reassigning {len(assigned_tunnels)} tunnels from {client_id} to {my_id}.")
                    for tunnel in assigned_tunnels:
                        tunnel['assigned_client_id'] = my_id
                        self.config_manager.update_object(tunnel['id'], tunnel)
                    self.refresh_dashboard() # Update dashboard as tunnel assignments changed
                # If user chose not to reassign, tunnels remain assigned to the (now removed) client ID

            # Proceed with removal from Syncthing and Config
            try:
                 # Remove from Syncthing first
                 self.syncthing_manager.remove_device(client_id)
                 logging.info(f"Successfully removed device {client_id} from Syncthing.")
            except Exception as e:
                 logging.error(f"Error removing device from Syncthing {client_id}: {e}", exc_info=True)
                 # Decide whether to continue or stop if Syncthing fails
                 # Show error but *continue* to remove from local config
                 self.show_error(f"Error communicating with Syncthing to remove device. It might reappear if other devices still have it. Check Syncthing logs.")

            # Find the client object in our config *using syncthing_id*
            client_to_delete_config_id = None
            for cfg_id, cfg_obj in self.config_manager.get_all_objects().items():
                if cfg_obj.get('type') == 'client' and cfg_obj.get('syncthing_id') == client_id:
                     client_to_delete_config_id = cfg_id
                     break

            if client_to_delete_config_id:
                deleted_cfg = self.config_manager.delete_object(client_to_delete_config_id)
                if deleted_cfg:
                     logging.info(f"Deleted client config object {client_to_delete_config_id}")
                else:
                     # This shouldn't happen if found above, but log just in case
                     logging.warning(f"Failed to delete client config object {client_to_delete_config_id} found for Syncthing ID {client_id}")
            else:
                 logging.warning(f"No client config object found for Syncthing ID {client_id} to delete.")


            # Refresh SettingsView where the device list is
            if "SettingsView" in self.frames:
                self.frames["SettingsView"].enter()

    # History View Passthroughs
    def get_history_file_index(self): return self.config_manager.get_history_file_index()
    def get_file_version_history(self, file_id): return self.config_manager.get_file_version_history(file_id)
    def get_file_content_at_version(self, file_id, timestamp): return self.config_manager.get_file_content_at_version(file_id, timestamp)
    