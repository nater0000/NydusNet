import customtkinter as ctk
import qrcode
from PIL import Image
import logging
import re
import os

class ToolTip(ctk.CTkToplevel):
    """
    A tooltip window that appears after a delay when hovering over a widget.
    """
    def __init__(self, widget, text, delay=500): # Default delay 500ms
        self.show_after_id = None # ID for the scheduled 'show' task
        self.delay = delay # Time in ms before showing
        self._is_valid = False # Flag to track if tooltip is properly initialized

        try:
            # Ensure the parent widget exists before proceeding
            if not widget or not widget.winfo_exists():
                logging.warning("ToolTip's parent widget does not exist. Aborting creation.")
                return # Do not proceed if widget is invalid

            super().__init__(widget)
            self.widget = widget
            self.text = text

            self.withdraw() # Start hidden
            self.overrideredirect(True) # No window decorations (border, title bar)

            # Configure the label appearance
            self.label = ctk.CTkLabel(self, text=self.text, corner_radius=5,
                                      fg_color=("#3D3D3D", "#4D4D4D"), # Dark gray background
                                      text_color=("white", "white"), # White text
                                      wraplength=200, # Max width before wrapping
                                      justify="left") # Align text left
            self.label.pack(ipadx=5, ipady=3) # Internal padding

            # Bind events to schedule/cancel showing and hiding
            self.widget.bind("<Enter>", self.schedule_show, add="+")
            self.widget.bind("<Leave>", self.cancel_show_and_hide, add="+")
            # Hide tooltip if the parent widget is destroyed
            self.widget.bind("<Destroy>", lambda e: self.destroy(), add="+")

            self._is_valid = True # Mark as successfully initialized

        except Exception as e:
            self._is_valid = False
            logging.warning(f"ToolTip creation failed: {e}", exc_info=True)
            # Attempt to destroy self if partially created
            if self.winfo_exists():
                try:
                    self.destroy()
                except Exception:
                    pass # Ignore errors during cleanup

    def schedule_show(self, event=None):
        """Schedules the tooltip to appear after the specified delay."""
        if not self._is_valid: return
        self.cancel_show() # Cancel any previously scheduled show
        self.show_after_id = self.after(self.delay, self.show)

    def cancel_show(self):
        """Cancels a pending tooltip show task."""
        if self.show_after_id:
            try:
                self.after_cancel(self.show_after_id)
            except Exception:
                 pass # Ignore if ID is invalid
            self.show_after_id = None

    def show(self, event=None):
        """Calculates position and displays the tooltip."""
        self.show_after_id = None # Clear scheduled ID as it's running now
        if not self._is_valid or not hasattr(self, 'widget') or not self.widget.winfo_exists() or not self.winfo_exists():
            return # Abort if widget or tooltip destroyed

        try:
            # Get widget position and dimensions
            x = self.widget.winfo_rootx() + 5 # Small offset from left edge
            widget_y = self.widget.winfo_rooty()
            widget_height = self.widget.winfo_height()

            # Calculate preferred position (below widget)
            preferred_y = widget_y + widget_height + 5

            # Update tooltip geometry to get its required height
            self.update_idletasks()
            tip_height = self.winfo_reqheight()
            tip_width = self.winfo_reqwidth() # Get width too

            # Adjust if tooltip goes off bottom of screen
            screen_height = self.winfo_screenheight()
            if preferred_y + tip_height > screen_height:
                y = widget_y - tip_height - 5 # Position above widget
            else:
                y = preferred_y

            # Adjust if tooltip goes off right edge of screen
            screen_width = self.winfo_screenwidth()
            if x + tip_width > screen_width:
                 x = screen_width - tip_width - 5 # Align to right edge

            # Ensure coordinates are non-negative
            x = max(0, x)
            y = max(0, y)

            self.geometry(f"+{x}+{y}")
            self.deiconify() # Show the tooltip window
            self.lift() # Bring it to the top

        except Exception as e:
            logging.debug(f"Tooltip show calculation/display failed: {e}")
            self.withdraw() # Ensure it's hidden on error

    def cancel_show_and_hide(self, event=None):
        """Cancels any pending show and hides the tooltip immediately."""
        self.cancel_show()
        self.hide()

    def hide(self, event=None):
        """Hides the tooltip window."""
        if not self._is_valid or not self.winfo_exists(): return
        try:
            self.withdraw()
        except Exception:
            pass # Ignore errors if window is already gone

    def destroy(self):
        """Safely destroys the tooltip and unbinds events."""
        if not hasattr(self, '_is_valid') or not self._is_valid:
            # If initialization failed or already destroyed, just ensure super is called if possible
            if self.winfo_exists():
                 try: super().destroy()
                 except Exception: pass
            return

        self._is_valid = False # Mark as destroyed
        self.cancel_show() # Cancel any pending show timer

        # Safely unbind events from the parent widget
        if hasattr(self, 'widget') and self.widget and self.widget.winfo_exists():
            try:
                self.widget.unbind("<Enter>")
                self.widget.unbind("<Leave>")
                self.widget.unbind("<Destroy>")
            except Exception:
                pass # Ignore errors if widget is gone

        # Destroy the Toplevel window itself
        if self.winfo_exists():
            try:
                super().destroy()
            except Exception as e:
                 logging.warning(f"Error during Tooltip super().destroy(): {e}")


class BaseDialog(ctk.CTkToplevel):
    """Base class for modal dialogs."""
    def __init__(self, parent, title="Dialog"):
        super().__init__(parent)
        self.title(title)
        self.result = None # Stores the dialog result (e.g., entered data, True/False)
        self._parent = parent # Reference to the parent window
        self._center_window_after_id = None # To store the ID of the centering task

        try:
            self.transient(parent) # Associate dialog with parent window
            self.grab_set() # Make dialog modal (block interaction with parent)
            self.protocol("WM_DELETE_WINDOW", self._on_cancel) # Handle window close ('X') button

            # Schedule centering task, store its ID
            self._center_window_after_id = self.after(50, self._center_window)

        except Exception as e:
            logging.error(f"Error initializing BaseDialog: {e}", exc_info=True)
            # Ensure dialog is destroyed if init fails partially
            if self.winfo_exists(): self.destroy()


    def _center_window(self):
        """Centers the dialog on the screen."""
        self._center_window_after_id = None # Clear the stored ID as the task is running

        # Abort if the window was destroyed before this could run
        if not self.winfo_exists():
            return

        try:
            self.update_idletasks() # Ensure dimensions are calculated
            width = self.winfo_width()
            height = self.winfo_height()
            screen_width = self.winfo_screenwidth()
            screen_height = self.winfo_screenheight()
            x = (screen_width - width) // 2
            y = (screen_height - height) // 2
            # Prevent negative coordinates if dialog is larger than screen
            x = max(0, x)
            y = max(0, y)
            self.geometry(f"+{x}+{y}")
        except Exception as e:
            logging.warning(f"Error centering dialog: {e}")

    def _on_ok(self, event=None):
        """Default action for 'OK' or 'Save' buttons."""
        # Result should be set by subclass before calling this
        self.destroy() # Consolidate cleanup in destroy

    def _on_cancel(self):
        """Default action for 'Cancel' or window close button."""
        self.result = None # Ensure result is None on cancel
        self.destroy() # Consolidate cleanup in destroy

    def get_input(self):
        """Waits for the dialog to close and returns the result."""
        # Only wait if the window still exists
        if self.winfo_exists():
             try:
                 self.wait_window()
             except Exception as e:
                  logging.warning(f"Error during wait_window: {e}") # Handle potential errors if destroyed unexpectedly
        return self.result

    def destroy(self):
        """Safely cancels pending tasks, releases grab, and destroys the window."""
        # 1. Cancel pending 'after' tasks
        if self._center_window_after_id:
            try:
                self.after_cancel(self._center_window_after_id)
            except Exception:
                pass # Task might already be cancelled or invalid
            self._center_window_after_id = None

        # 2. Safely release grab (if active)
        try:
            # Check grab_status only if window exists
            if self.winfo_exists() and self.grab_status() == "global":
                self.grab_release()
        except Exception:
            pass # Window might already be gone or grab failed

        # 3. Call the original CTkToplevel destroy only if it still exists
        if self.winfo_exists():
            try:
                super().destroy()
            except Exception as e:
                 logging.warning(f"Error during BaseDialog super().destroy(): {e}")


class UnlockDialog(BaseDialog):
    """Dialog for entering master password or setting it on first run."""
    def __init__(self, parent, first_run: bool = False, controller=None, title=None):
        # Ensure controller exists before proceeding
        if not controller:
            logging.critical("UnlockDialog requires a controller instance!")
            # Cannot proceed, maybe raise an error or handle differently
            super().__init__(parent, title="Error") # Init base to allow destroy
            ctk.CTkLabel(self, text="Internal Error: Controller missing.").pack(padx=20, pady=20)
            self.after(100, self.destroy)
            return

        self.controller = controller
        self.first_run = first_run
        title = title or ("Create Master Password" if first_run else "Unlock NydusNet")
        super().__init__(parent, title=title) # Call BaseDialog init

        # --- Load images via controller ---
        self.show_icon = None
        self.hide_icon = None
        self.bg_image = None
        self.use_image_icons = False
        try:
            if hasattr(self.controller, 'images') and self.controller.images:
                self.show_icon = self.controller.images.get("eye-show")
                self.hide_icon = self.controller.images.get("eye-hide")
                self.bg_image = self.controller.images.get("bg_gradient")

                # Check if essential icons were loaded (not red squares)
                # Assuming placeholder is a red square Image object
                placeholder_img = ctk.CTkImage(Image.new('RGB', (20,20), color='red'), size=(20,20))._light_image
                if self.show_icon and self.show_icon._light_image != placeholder_img and \
                   self.hide_icon and self.hide_icon._light_image != placeholder_img:
                    self.use_image_icons = True
                else:
                     raise ValueError("Eye icons loaded as placeholders.")
            else:
                raise ValueError("Controller images dictionary is missing or empty.")

        except Exception as e:
            logging.warning(f"UnlockDialog icons failed ({e}). Using text fallback.")
            self.show_icon = "👁️" # Text fallback
            self.hide_icon = "🔒" # Text fallback
            self.use_image_icons = False
            self.bg_image = None # Ensure no background if icons failed

        # --- UI Setup ---
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Background Image (Optional)
        if self.bg_image and self.bg_image._light_image != placeholder_img:
            self.bg_label = ctk.CTkLabel(self, text="", image=self.bg_image)
            self.bg_label.grid(row=0, column=0, sticky="nsew")
            # Determine fg_color based on appearance mode for better contrast on background
            bg_frame_fg = ctk.ThemeManager.theme["CTkFrame"]["fg_color"]
        else:
             # Use default frame background if no image
            bg_frame_fg = "transparent"

        # Centered Content Frame
        self.main_frame = ctk.CTkFrame(self, corner_radius=10, fg_color=bg_frame_fg)
        self.main_frame.grid(row=0, column=0, padx=30, pady=30, sticky="")

        self.geometry("400x300") # Fixed size
        self.resizable(False, False)

        # Create specific UI elements (unlock or setup)
        if self.first_run:
            self._create_password_setup_ui()
        else:
            self._create_unlock_ui()

        # Center window after widgets are created (BaseDialog already schedules this)

    def _toggle_password_visibility(self, entry, button):
        if not entry or not button: return
        try:
            if entry.cget("show") == "*":
                entry.configure(show="")
                button.configure(image=self.hide_icon if self.use_image_icons else None,
                                 text=self.hide_icon if not self.use_image_icons else "")
            else:
                entry.configure(show="*")
                button.configure(image=self.show_icon if self.use_image_icons else None,
                                 text=self.show_icon if not self.use_image_icons else "")
        except Exception as e:
             logging.warning(f"Error toggling password visibility: {e}")


    def _create_unlock_ui(self):
        ctk.CTkLabel(self.main_frame, text="NydusNet", font=ctk.CTkFont(size=20, weight="bold")).pack(padx=30, pady=(30, 10))
        ctk.CTkLabel(self.main_frame, text="Enter Master Password:").pack(padx=30, pady=(10, 0))

        entry_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        entry_frame.pack(padx=30, pady=10)

        self.entry1 = ctk.CTkEntry(entry_frame, show="*", width=200)
        self.entry1.pack(side="left")
        self.entry1.bind("<Return>", self._on_ok)
        # Focus is set by app.py using after(50, ...)

        toggle_btn1 = ctk.CTkButton(entry_frame, image=self.show_icon if self.use_image_icons else None,
                                    text=self.show_icon if not self.use_image_icons else "",
                                    width=28, anchor="center", # Center icon/text
                                    command=lambda: self._toggle_password_visibility(self.entry1, toggle_btn1))
        toggle_btn1.pack(side="left", padx=(5, 0))

        button_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        button_frame.pack(padx=30, pady=(10, 20))

        ctk.CTkButton(button_frame, text="Unlock", command=self._on_ok, width=110).pack(side="left", padx=5)
        ctk.CTkButton(button_frame, text="Forgot Password?", command=self._on_forgot, width=110, fg_color="transparent", border_width=1).pack(side="left", padx=5)

    def _create_password_setup_ui(self):
        ctk.CTkLabel(self.main_frame, text="Welcome to NydusNet", font=ctk.CTkFont(size=20, weight="bold")).pack(padx=30, pady=(30, 10))
        ctk.CTkLabel(self.main_frame, text="Create a New Master Password:").pack(padx=30, pady=(10, 0))

        entry_frame1 = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        entry_frame1.pack(padx=30, pady=5)
        self.entry1 = ctk.CTkEntry(entry_frame1, show="*", width=200)
        self.entry1.pack(side="left")
        # Focus is set by app.py using after(50, ...)
        toggle_btn1 = ctk.CTkButton(entry_frame1, image=self.show_icon if self.use_image_icons else None, text=self.show_icon if not self.use_image_icons else "", width=28, anchor="center", command=lambda: self._toggle_password_visibility(self.entry1, toggle_btn1))
        toggle_btn1.pack(side="left", padx=(5, 0))

        ctk.CTkLabel(self.main_frame, text="Confirm Master Password:").pack(padx=30, pady=(10, 0))
        entry_frame2 = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        entry_frame2.pack(padx=30, pady=5)
        self.entry2 = ctk.CTkEntry(entry_frame2, show="*", width=200)
        self.entry2.pack(side="left")
        self.entry2.bind("<Return>", self._on_ok)
        toggle_btn2 = ctk.CTkButton(entry_frame2, image=self.show_icon if self.use_image_icons else None, text=self.show_icon if not self.use_image_icons else "", width=28, anchor="center", command=lambda: self._toggle_password_visibility(self.entry2, toggle_btn2))
        toggle_btn2.pack(side="left", padx=(5, 0))

        ctk.CTkLabel(self.main_frame, text="Allowed: A-Z a-z 0-9 Space !@#$%^&*()_+-=[]{}|;:,.<>?", font=("", 10), wraplength=250).pack(padx=30, pady=5)
        ctk.CTkButton(self.main_frame, text="Create", command=self._on_ok, width=230).pack(padx=30, pady=20)

    def _on_ok(self, event=None):
        # Validate password input
        password = self.entry1.get() # Get password from first entry
        if self.first_run:
            password2 = self.entry2.get()
            # Regex includes space now
            allowed_chars = r"^[A-Za-z0-9 !@#$%^&*()_+\-=\[\]{}|;:,.<>?]*$"
            if password != password2:
                ErrorDialog(self, message="Passwords do not match.")
                return # Keep dialog open
            if not password: # Check if empty
                ErrorDialog(self, message="Password cannot be empty.")
                return
            if not re.fullmatch(allowed_chars, password):
                ErrorDialog(self, message="Password contains invalid characters.\nAllowed: A-Z a-z 0-9 Space !@#$%^&*()_+-=[]{}|;:,.<>?")
                return

        # If validation passes (or not first run), set result and close
        self.result = password
        super()._on_ok() # Calls BaseDialog._on_ok -> BaseDialog.destroy

    def _on_forgot(self):
        self.result = None # Ensure result is None if flow continues elsewhere
        if self.controller:
            logging.info("Forgot password button clicked.")
            # Destroy *this* dialog first to avoid multiple modals
            self.destroy()
            # Use 'after' to schedule the next step after this dialog is gone
            self.controller.after(50, self.controller.forgot_password)
        else:
             logging.warning("Forgot password clicked but no controller found.")
             self.destroy() # Just close


class LoadingDialog(BaseDialog):
    """Modal dialog showing an indeterminate progress bar."""
    def __init__(self, parent, title="Loading..."):
        super().__init__(parent, title=title)
        self.geometry("400x300")
        self.resizable(False, False)

        # Center content using grid
        self.grid_rowconfigure(0, weight=1) # Space above
        self.grid_rowconfigure(3, weight=1) # Space below
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self, text="Initializing NydusNet...", font=ctk.CTkFont(size=16)).grid(row=0, column=0, padx=40, pady=(40, 10), sticky="s")

        self.progressbar = ctk.CTkProgressBar(self, mode="indeterminate")
        self.progressbar.grid(row=1, column=0, padx=40, pady=10, sticky="ew")
        self.progressbar.start() # Start animation

        ctk.CTkLabel(self, text="Please wait...", text_color="gray60").grid(row=2, column=0, padx=40, pady=(0, 40), sticky="n")

        self.protocol("WM_DELETE_WINDOW", lambda: None) # Prevent user from closing

        # BaseDialog already schedules centering

    def destroy(self):
        """Override destroy to stop the progress bar animation."""
        if hasattr(self, 'progressbar'):
            try:
                self.progressbar.stop()
            except Exception as e:
                 logging.warning(f"Error stopping progress bar: {e}")
        super().destroy() # Call BaseDialog's safe destroy


class ProvisionDialog(BaseDialog):
    """Dialog to get sudo credentials for server provisioning."""
    def __init__(self, parent, server_name, server_ip):
        super().__init__(parent, title=f"Setup Server: {server_name}")
        # Main frame for content padding
        content_frame = ctk.CTkFrame(self, fg_color="transparent")
        content_frame.pack(padx=20, pady=20, fill="both", expand=True)

        ctk.CTkLabel(content_frame, text=f"Enter administrative credentials for {server_ip}.\nThese are used once for setup and are NOT saved.",
                     wraplength=350, justify="left").pack(pady=(0, 15))

        ctk.CTkLabel(content_frame, text="Sudo Username:").pack(anchor="w")
        self.user_entry = ctk.CTkEntry(content_frame, width=250)
        self.user_entry.pack(pady=(0, 10), fill="x")
        self.user_entry.insert(0, "root") # Default user

        ctk.CTkLabel(content_frame, text="Sudo Password:").pack(anchor="w")
        self.pass_entry = ctk.CTkEntry(content_frame, show="*", width=250)
        self.pass_entry.pack(pady=(0, 15), fill="x")
        self.pass_entry.bind("<Return>", self._on_ok) # Allow Enter to submit

        # Focus password entry after dialog appears
        self.after(100, self.pass_entry.focus_set)

        button_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
        button_frame.pack(pady=(10, 0))
        ctk.CTkButton(button_frame, text="Begin Setup", command=self._on_ok).pack(side="left", padx=10)
        ctk.CTkButton(button_frame, text="Cancel", command=self._on_cancel).pack(side="left", padx=10)

    def _on_ok(self, event=None):
        user = self.user_entry.get().strip()
        password = self.pass_entry.get() # Don't strip password
        if not user or not password:
            ErrorDialog(self, message="Username and Password are required.")
            return # Keep dialog open
        self.result = {"user": user, "password": password}
        super()._on_ok() # Close dialog


class ProvisioningLogDialog(BaseDialog):
    """Dialog to display logs during server provisioning."""
    def __init__(self, parent, server_name):
        super().__init__(parent, title=f"Setting up {server_name}...")
        self.geometry("600x400")
        # Prevent closing until provisioning completes or fails
        self.protocol("WM_DELETE_WINDOW", lambda: logging.warning("Attempted to close provisioning log during operation."))

        self.textbox = ctk.CTkTextbox(self, wrap="none", font=("Courier New", 11)) # Monospaced font, no wrap
        self.textbox.pack(expand=True, fill="both", padx=10, pady=(10, 5))
        self.textbox.configure(state="disabled") # Read-only

        self.status_label = ctk.CTkLabel(self, text="Provisioning in progress...")
        self.status_label.pack(pady=5)

        self.close_button = ctk.CTkButton(self, text="Close", command=self._on_cancel, state="disabled")
        self.close_button.pack(pady=10)

    def update_log(self, log_lines):
        """Updates the textbox content safely."""
        if not self.winfo_exists(): return # Abort if window destroyed

        try:
            self.textbox.configure(state="normal")
            # Efficient update: replace content only if it changed
            # current_content = self.textbox.get("1.0", "end-1c") # Less efficient for long logs
            new_content = "\n".join(log_lines)
            # if current_content != new_content:
            self.textbox.delete("1.0", "end")
            self.textbox.insert("1.0", new_content)
            self.textbox.see("end") # Auto-scroll to bottom
            self.textbox.configure(state="disabled")
        except Exception as e:
            logging.error(f"Error updating provisioning log: {e}")
            # Ensure textbox is disabled even on error
            if self.winfo_exists(): self.textbox.configure(state="disabled")


    def complete(self, success):
        """Updates status label and enables close button on completion."""
        if not self.winfo_exists(): return # Abort if window destroyed

        if success:
            self.status_label.configure(text="✅ Setup Complete!", text_color="green")
        else:
            self.status_label.configure(text="❌ Setup Failed. Check logs above for details.", text_color="red")
        self.close_button.configure(state="normal") # Enable close button
        # Allow closing via 'X' button now
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)


class ServerDialog(BaseDialog):
    """Dialog for adding or editing server details."""
    def __init__(self, parent, title="Server Details", initial_data=None):
        super().__init__(parent, title=title)
        self.initial_data = initial_data or {}

        # Use a frame for padding
        content_frame = ctk.CTkFrame(self, fg_color="transparent")
        content_frame.pack(padx=20, pady=20, fill="both", expand=True)

        content_frame.grid_columnconfigure(1, weight=1) # Allow entry fields to expand

        # Server Name
        ctk.CTkLabel(content_frame, text="Server Name:").grid(row=0, column=0, padx=(0,10), pady=5, sticky="w")
        self.name_entry = ctk.CTkEntry(content_frame)
        self.name_entry.grid(row=0, column=1, pady=5, sticky="ew")
        self.name_entry.insert(0, self.initial_data.get("name", ""))

        # IP Address
        ctk.CTkLabel(content_frame, text="IP Address:").grid(row=1, column=0, padx=(0,10), pady=5, sticky="w")
        self.ip_entry = ctk.CTkEntry(content_frame)
        self.ip_entry.grid(row=1, column=1, pady=5, sticky="ew")
        self.ip_entry.insert(0, self.initial_data.get("ip_address", ""))

        # Tunnel Username (Optional Override)
        ctk.CTkLabel(content_frame, text="Tunnel User:").grid(row=2, column=0, padx=(0,10), pady=5, sticky="w")
        self.tunnel_user_entry = ctk.CTkEntry(content_frame)
        self.tunnel_user_entry.grid(row=2, column=1, pady=5, sticky="ew")
        self.tunnel_user_entry.insert(0, self.initial_data.get("tunnel_user", ""))
        ToolTip(self.tunnel_user_entry, "Optional: Override the default 'tunnel' user used for SSH connections. Leave blank for default.")

        # Manual Provision Override Checkbox
        self.provisioned_var = ctk.BooleanVar(value=self.initial_data.get("is_provisioned", False))
        self.provisioned_check = ctk.CTkCheckBox(content_frame, text="Mark as Setup Complete (Manual Override)",
                                                 variable=self.provisioned_var)
        self.provisioned_check.grid(row=3, column=0, columnspan=2, padx=0, pady=10, sticky="w")
        ToolTip(self.provisioned_check, "Manually mark this server as ready for tunnels, skipping automated setup steps.")

        # Buttons
        button_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
        button_frame.grid(row=4, column=0, columnspan=2, pady=(15, 0)) # Add padding above buttons
        ctk.CTkButton(button_frame, text="Save", command=self._on_ok).pack(side="left", padx=10)
        ctk.CTkButton(button_frame, text="Cancel", command=self._on_cancel).pack(side="left", padx=10)

        # Focus name entry initially
        self.after(100, self.name_entry.focus_set)

    def _on_ok(self, event=None):
        name = self.name_entry.get().strip()
        ip_address = self.ip_entry.get().strip()
        tunnel_user = self.tunnel_user_entry.get().strip() # Use empty string if blank
        is_provisioned = self.provisioned_var.get()

        if not name:
            ErrorDialog(self, message="Server Name is required.")
            return
        if not ip_address:
             ErrorDialog(self, message="IP Address is required.")
             return

        # Basic IP/domain validation (very lenient)
        if not re.match(r"^[a-zA-Z0-9\.\-:]+$", ip_address):
             ErrorDialog(self, message="Invalid characters in IP Address or Hostname.")
             return

        # Prepare result dictionary
        self.result = self.initial_data.copy() # Start with existing data
        self.result.update({
            "name": name,
            "ip_address": ip_address,
            "tunnel_user": tunnel_user,
            "is_provisioned": is_provisioned,
            "type": "server" # Ensure type is set
        })
        super()._on_ok() # Close dialog


class TunnelDialog(BaseDialog):
    """Dialog for adding or editing tunnel configuration."""
    def __init__(self, parent, controller, title="Tunnel Details", initial_data=None):
        super().__init__(parent, title=title)
        self.controller = controller
        self.initial_data = initial_data or {}

        # Use a frame for padding
        content_frame = ctk.CTkFrame(self, fg_color="transparent")
        content_frame.pack(padx=20, pady=20, fill="both", expand=True)

        content_frame.grid_columnconfigure(1, weight=1) # Entry/menu column expands

        # Server Selection
        ctk.CTkLabel(content_frame, text="Server:").grid(row=0, column=0, padx=(0,10), pady=5, sticky="w")
        self.server_map = {s['name']: s['id'] for s in self.controller.get_servers() if s.get('is_provisioned')}
        server_names = sorted(list(self.server_map.keys())) or ["No provisioned servers available"]
        self.server_menu = ctk.CTkOptionMenu(content_frame, values=server_names)
        self.server_menu.grid(row=0, column=1, pady=5, sticky="ew")
        if not self.server_map: self.server_menu.configure(state="disabled")

        # Managed By (Device Selection)
        ctk.CTkLabel(content_frame, text="Managed By:").grid(row=1, column=0, padx=(0,10), pady=5, sticky="w")
        self.client_map, client_names = self.controller.get_clients_for_dropdown()
        self.client_menu = ctk.CTkOptionMenu(content_frame, values=client_names)
        self.client_menu.grid(row=1, column=1, pady=5, sticky="ew")
        if not client_names: self.client_menu.configure(state="disabled", values=["Initializing..."])

        # Hostname Entry
        ctk.CTkLabel(content_frame, text="Hostname:").grid(row=2, column=0, padx=(0,10), pady=5, sticky="w")
        hostname_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
        hostname_frame.grid(row=2, column=1, pady=5, sticky="ew")
        hostname_frame.grid_columnconfigure(0, weight=1) # Make entry expand
        self.hostname_entry = ctk.CTkEntry(hostname_frame)
        self.hostname_entry.grid(row=0, column=0, sticky="ew")
        hostname_help = ctk.CTkLabel(hostname_frame, text="?", width=20, cursor="hand2")
        hostname_help.grid(row=0, column=1, padx=(5,0))
        ToolTip(hostname_help, "A friendly name for this tunnel (e.g., 'plex', 'web-app'). Used for display only.")

        # Remote Port Entry
        ctk.CTkLabel(content_frame, text="Remote Port:").grid(row=3, column=0, padx=(0,10), pady=5, sticky="w")
        remote_port_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
        remote_port_frame.grid(row=3, column=1, pady=5, sticky="ew")
        remote_port_frame.grid_columnconfigure(0, weight=1)
        self.remote_port_entry = ctk.CTkEntry(remote_port_frame)
        self.remote_port_entry.grid(row=0, column=0, sticky="ew")
        remote_port_help = ctk.CTkLabel(remote_port_frame, text="?", width=20, cursor="hand2")
        remote_port_help.grid(row=0, column=1, padx=(5,0))
        ToolTip(remote_port_help, "The public port on your server that will receive traffic (e.g., 80, 443, 8080). This port must be unique per server.")

        # Local Destination Entry
        ctk.CTkLabel(content_frame, text="Local Destination:").grid(row=4, column=0, padx=(0,10), pady=5, sticky="w")
        local_dest_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
        local_dest_frame.grid(row=4, column=1, pady=5, sticky="ew")
        local_dest_frame.grid_columnconfigure(0, weight=1)
        self.local_dest_entry = ctk.CTkEntry(local_dest_frame)
        self.local_dest_entry.grid(row=0, column=0, sticky="ew")
        local_dest_help = ctk.CTkLabel(local_dest_frame, text="?", width=20, cursor="hand2")
        local_dest_help.grid(row=0, column=1, padx=(5,0))
        ToolTip(local_dest_help, "Local address and port of the service (e.g., 'localhost:3000', '192.168.1.50:8123'). Use localhost:PORT if service is on the managing PC.")

        # Set initial values from initial_data or defaults
        if self.initial_data.get("server_id"):
             for name, sid in self.server_map.items():
                if sid == self.initial_data["server_id"]:
                    self.server_menu.set(name); break
        if self.initial_data.get("assigned_client_id"):
            for name, cid in self.client_map.items():
                if cid == self.initial_data["assigned_client_id"]:
                    self.client_menu.set(name); break
        else: # Default to "This Device" if creating new or unassigned
            my_name = f"{self.controller.get_my_device_name()} (This Device)"
            if my_name in client_names:
                self.client_menu.set(my_name)

        self.hostname_entry.insert(0, self.initial_data.get("hostname", ""))
        self.remote_port_entry.insert(0, str(self.initial_data.get("remote_port", "")))
        self.local_dest_entry.insert(0, self.initial_data.get("local_destination", "localhost:8080")) # Default

        # Enabled Checkbox
        self.enabled_var = ctk.BooleanVar(value=self.initial_data.get("enabled", False))
        self.enabled_check = ctk.CTkCheckBox(content_frame, text="Start tunnel automatically when app starts", variable=self.enabled_var)
        self.enabled_check.grid(row=5, column=1, padx=0, pady=10, sticky="w") # Align left under entry

        # Buttons
        button_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
        button_frame.grid(row=6, column=0, columnspan=2, pady=(15, 0)) # Padding above buttons
        ctk.CTkButton(button_frame, text="Save", command=self._on_ok).pack(side="left", padx=10)
        ctk.CTkButton(button_frame, text="Cancel", command=self._on_cancel).pack(side="left", padx=10)

        # Focus hostname entry initially
        self.after(100, self.hostname_entry.focus_set)


    def _on_ok(self, event=None):
        try:
            selected_server_name = self.server_menu.get()
            selected_client_name = self.client_menu.get()

            # Validate selections
            if not self.server_map or selected_server_name not in self.server_map:
                ErrorDialog(self, message="A valid 'Server' (must be set up/provisioned) must be selected.")
                return
            if not self.client_map or selected_client_name not in self.client_map:
                 ErrorDialog(self, message="A valid device ('Managed By') must be selected.")
                 return

            server_id = self.server_map.get(selected_server_name)
            client_id = self.client_map.get(selected_client_name)

            # Get and validate inputs
            hostname = self.hostname_entry.get().strip()
            remote_port_str = self.remote_port_entry.get().strip()
            local_destination = self.local_dest_entry.get().strip()

            if not hostname:
                ErrorDialog(self, message="Hostname is required.")
                return
            if not remote_port_str:
                ErrorDialog(self, message="Remote Port is required.")
                return
            if not local_destination:
                 ErrorDialog(self, message="Local Destination is required.")
                 return

            # Validate Remote Port
            try:
                remote_port = int(remote_port_str)
                if not (1 <= remote_port <= 65535): # Common port range
                    raise ValueError("Port out of valid range 1-65535")
            except ValueError:
                ErrorDialog(self, message="Invalid Remote Port: Must be a number between 1 and 65535.")
                return

            # Validate Local Destination format (host:port)
            parts = local_destination.split(':')
            if len(parts) != 2:
                ErrorDialog(self, message="Local Destination must be in the format host:port (e.g., localhost:3000 or 192.168.1.5:80).")
                return
            local_host, local_port_str = parts[0].strip(), parts[1].strip()
            if not local_host:
                 ErrorDialog(self, message="Local Destination host part cannot be empty.")
                 return
            try:
                local_port = int(local_port_str)
                if not (1 <= local_port <= 65535):
                     raise ValueError("Local port out of valid range 1-65535")
            except ValueError:
                 ErrorDialog(self, message="Invalid Local Destination Port: Must be a number between 1 and 65535.")
                 return

            # Update result dictionary
            self.result = self.initial_data.copy()
            self.result.update({
                "type": "tunnel",
                "server_id": server_id,
                "assigned_client_id": client_id,
                "hostname": hostname,
                "remote_port": remote_port,
                "local_destination": f"{local_host}:{local_port}", # Use cleaned parts
                "enabled": self.enabled_var.get()
            })
            super()._on_ok() # Close dialog if validation passes
        except Exception as e:
            logging.error(f"Unexpected error in Tunnel Dialog _on_ok: {e}", exc_info=True)
            ErrorDialog(self, message=f"An unexpected error occurred: {e}")


class InviteDialog(BaseDialog):
    """Dialog to display QR code and invite string for adding a new device."""
    def __init__(self, parent, invite_string: str):
        super().__init__(parent, title="Add a New Device")
        content_frame = ctk.CTkFrame(self, fg_color="transparent")
        content_frame.pack(padx=20, pady=20, fill="both", expand=True)

        ctk.CTkLabel(content_frame, text="On the new device, go to Settings > Devices > Invite Another Device,\nthen scan this QR code or paste the ID below:",
                     wraplength=400, justify="left").pack(pady=(0, 15))

        # Generate and display QR code
        try:
            qr_img_pil = qrcode.make(invite_string).resize((250, 250))
            self.qr_photo = ctk.CTkImage(light_image=qr_img_pil, dark_image=qr_img_pil, size=(250, 250))
            qr_label = ctk.CTkLabel(content_frame, image=self.qr_photo, text="")
            qr_label.pack(pady=10)
        except Exception as e:
            logging.error(f"Failed to generate QR code: {e}")
            ctk.CTkLabel(content_frame, text="Error generating QR code.", text_color="red").pack(pady=10)

        # Display invite string in a read-only entry
        ctk.CTkLabel(content_frame, text="Device ID:").pack(anchor="w", padx=10, pady=(10, 0))
        invite_entry = ctk.CTkEntry(content_frame, width=400)
        invite_entry.insert(0, invite_string)
        invite_entry.configure(state="readonly")
        invite_entry.pack(padx=10, pady=(0, 15))

        ctk.CTkButton(content_frame, text="Close", command=self._on_cancel, width=100).pack(pady=10)


class ConfirmationDialog(BaseDialog):
    """Simple Yes/No confirmation dialog."""
    def __init__(self, parent, title="Confirm", message="Are you sure?"):
        super().__init__(parent, title=title)
        content_frame = ctk.CTkFrame(self, fg_color="transparent")
        content_frame.pack(padx=20, pady=20, fill="both", expand=True)

        ctk.CTkLabel(content_frame, text=message, wraplength=300, justify="center").pack(pady=(0, 20))

        button_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
        button_frame.pack(pady=10)
        ctk.CTkButton(button_frame, text="Yes", command=self._on_ok, width=80).pack(side="left", padx=10)
        ctk.CTkButton(button_frame, text="No", command=self._on_cancel, width=80).pack(side="left", padx=10)

        self.resizable(False, False)

    def _on_ok(self, event=None):
        self.result = True
        super()._on_ok()


class RecoveryKeyDialog(BaseDialog):
    """Dialog to display or input the recovery key."""
    def __init__(self, parent, recovery_key: str = None, input_mode: bool = False, title=None):
        self.input_mode = input_mode
        title = title or ("Enter Recovery Key" if input_mode else "Save Your Recovery Key!")
        super().__init__(parent, title=title)

        content_frame = ctk.CTkFrame(self, fg_color="transparent")
        content_frame.pack(padx=20, pady=20, fill="both", expand=True)

        if input_mode:
            # UI for entering the key
            ctk.CTkLabel(content_frame, text="Enter your recovery key to reset your password:",
                         wraplength=350, justify="left").pack(pady=(0, 10))
            self.key_entry = ctk.CTkEntry(content_frame, width=350, font=("Courier New", 14))
            self.key_entry.pack(pady=10)
            self.after(100, self.key_entry.focus_set) # Focus entry
            self.key_entry.bind("<Return>", self._on_ok)

            button_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
            button_frame.pack(pady=20)
            ctk.CTkButton(button_frame, text="Reset Password", command=self._on_ok).pack(side="left", padx=10)
            ctk.CTkButton(button_frame, text="Cancel", command=self._on_cancel).pack(side="left", padx=10)
        else:
            # UI for displaying the key
            ctk.CTkLabel(content_frame, text="IMPORTANT:\nSave this recovery key in a secure place (e.g., password manager)!\nIt's the *only* way to reset your password if forgotten.",
                         wraplength=350, justify="left", text_color=("red", "orange")).pack(pady=(0, 10)) # Emphasize importance

            key_entry = ctk.CTkEntry(content_frame, width=350, font=("Courier New", 14))
            key_entry.insert(0, recovery_key if recovery_key else "ERROR: Key not provided!")
            key_entry.configure(state="readonly")
            key_entry.pack(pady=10)

            self.confirm_check_var = ctk.StringVar(value="off")
            confirm_check = ctk.CTkCheckBox(content_frame, text="I have securely saved this recovery key.",
                                            variable=self.confirm_check_var, onvalue="on", offvalue="off",
                                            command=self._check_state) # Command calls check_state
            confirm_check.pack(pady=10)

            self.ok_button = ctk.CTkButton(content_frame, text="Continue", command=self._on_ok, state="disabled")
            self.ok_button.pack(pady=15)
            # self.confirm_check_var.trace_add("write", self._check_state) # Using command is simpler

        self.resizable(False, False)

    def _check_state(self, *args):
        """Enables/disables the Continue button based on the checkbox state (display mode only)."""
        if not self.input_mode and hasattr(self, 'ok_button'):
            is_checked = self.confirm_check_var.get() == "on"
            self.ok_button.configure(state="normal" if is_checked else "disabled")

    def _on_ok(self, event=None):
        if self.input_mode:
            # Return the entered key, stripped of whitespace
            self.result = self.key_entry.get().strip() if hasattr(self, 'key_entry') else None
            if not self.result:
                 ErrorDialog(self, "Recovery key cannot be empty.")
                 return # Keep dialog open
        else: # Display mode
             if self.confirm_check_var.get() == "on":
                 self.result = True # Confirmed saving
             else:
                 ErrorDialog(self, "Please confirm you have securely saved the recovery key before continuing.")
                 return # Keep dialog open

        super()._on_ok() # Close dialog if checks pass


class ErrorDialog(BaseDialog):
    """Simple dialog to display an error message."""
    def __init__(self, parent, message: str, title: str = "Error"):
        super().__init__(parent, title=title)
        content_frame = ctk.CTkFrame(self, fg_color="transparent")
        content_frame.pack(padx=20, pady=20, fill="both", expand=True)

        # Optional: Add error icon (using text emoji)
        ctk.CTkLabel(content_frame, text="⚠️", font=ctk.CTkFont(size=24)).pack(pady=(0, 10))

        # Display the error message
        ctk.CTkLabel(content_frame, text=message, wraplength=300, justify="center").pack(pady=(0, 20))

        # OK button
        ok_button = ctk.CTkButton(content_frame, text="OK", command=self._on_ok, width=100)
        ok_button.pack(pady=10)

        # Focus the OK button after the dialog appears
        self.after(50, ok_button.focus_set)
        self.resizable(False, False)


class LogViewerDialog(BaseDialog):
    """Dialog to display multiline text content, like logs."""
    def __init__(self, parent, log_content: str, title: str = "Log Viewer"):
        super().__init__(parent, title=title)
        self.geometry("800x600") # Start with a reasonable size
        self.minsize(400, 300) # Allow resizing down to a minimum

        # Textbox fills the entire dialog
        textbox = ctk.CTkTextbox(self, wrap="none", font=("Courier New", 11)) # No wrapping, monospaced font
        textbox.pack(expand=True, fill="both", padx=10, pady=(10, 5))
        try:
            textbox.insert("1.0", log_content if log_content else "Log is empty.")
        except Exception as e:
            logging.error(f"Error inserting log content: {e}")
            textbox.insert("1.0", f"Error displaying log content:\n{e}")

        textbox.configure(state="disabled") # Make read-only

        # Close button at the bottom
        ctk.CTkButton(self, text="Close", command=self._on_cancel, width=100).pack(pady=10)
